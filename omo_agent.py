import copy
import json
import os
import shlex
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import with_prompt_template
from harbor.agents.installed.opencode import OpenCode
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class OMOAgent(OpenCode):

    def __init__(self, *args, omo_claude="no", omo_openai="no", omo_gemini="no",
                 omo_copilot="no", omo_opencode_zen="no", omo_opencode_go="yes",
                 omo_zai="no", omo_kimi="no", omo_vercel="no", **kwargs):
        super().__init__(*args, **kwargs)
        self._omo_flags = (
            f"--claude={omo_claude} --openai={omo_openai} --gemini={omo_gemini} "
            f"--copilot={omo_copilot} --opencode-zen={omo_opencode_zen} "
            f"--opencode-go={omo_opencode_go} --zai-coding-plan={omo_zai} "
            f"--kimi-for-coding={omo_kimi} --vercel-ai-gateway={omo_vercel}"
        )

    @staticmethod
    def name() -> str:
        return "omo-agent"

    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)
        await self.exec_as_root(environment,
            command="apt-get install -y unzip",
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )
        await self.exec_as_agent(environment,
            command=(
                "curl -fsSL https://bun.sh/install | bash && "
                'export BUN_INSTALL="$HOME/.bun" && '
                'export PATH="$BUN_INSTALL/bin:$PATH" && '
                "bun --version"
            ),
        )
        await self.exec_as_agent(environment,
            command=(
                '. ~/.nvm/nvm.sh && '
                'export BUN_INSTALL="$HOME/.bun" && '
                'export PATH="$BUN_INSTALL/bin:$PATH" && '
                f"bunx oh-my-openagent install --no-tui "
                f"{self._omo_flags} --skip-auth && "
                "cp ~/.config/opencode/opencode.json /logs/agent/opencode.json 2>/dev/null; "
                "cp ~/.config/opencode/oh-my-openagent.json /logs/agent/oh-my-openagent.json 2>/dev/null; "
                "true"
            ),
        )

    def _build_register_config_command(self) -> str | None:
        config: dict[str, Any] = {}

        if self.mcp_servers:
            for server in self.mcp_servers:
                if server.transport == "stdio":
                    cmd = [server.command] + server.args if server.command else []
                    config.setdefault("mcp", {})[server.name] = {"type": "local", "command": cmd}
                else:
                    config.setdefault("mcp", {})[server.name] = {"type": "remote", "url": server.url}

        if self.model_name and "/" in self.model_name:
            provider, model_id = self.model_name.split("/", 1)
            provider_config: dict[str, Any] = {"models": {model_id: {}}}
            base_url = os.environ.get("OPENAI_BASE_URL")
            if base_url and provider == "openai":
                provider_config.setdefault("options", {})["baseURL"] = base_url
            config["provider"] = {provider: provider_config}

        config = self._deep_merge(copy.deepcopy(self._DEFAULT_CONFIG), config)
        config = self._deep_merge(config, self._opencode_config)

        if not config:
            return None

        escaped = shlex.quote(json.dumps(config, indent=2))
        return (
            f"mkdir -p ~/.config/opencode && "
            f"echo {escaped} > ~/.config/opencode/opencode.json && "
            f"cp ~/.config/opencode/opencode.json /logs/agent/opencode.json 2>/dev/null"
        )

    @with_prompt_template
    async def run(self, instruction: str, environment: BaseEnvironment,
                  context: AgentContext) -> None:
        escaped_instruction = shlex.quote(instruction)
        env: dict[str, str] = {}
        keys: list[str] = []

        provider = self.model_name.split("/", 1)[0] if self.model_name and "/" in self.model_name else None

        if provider == "amazon-bedrock":
            keys.extend(["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"])
        elif provider == "anthropic":
            keys.append("ANTHROPIC_API_KEY")
        elif provider == "azure":
            keys.extend(["AZURE_RESOURCE_NAME", "AZURE_API_KEY"])
        elif provider == "deepseek":
            keys.append("DEEPSEEK_API_KEY")
        elif provider == "github-copilot":
            keys.append("GITHUB_TOKEN")
        elif provider == "google":
            keys.extend(["GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY",
                         "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
                         "GOOGLE_CLOUD_LOCATION", "GOOGLE_GENAI_USE_VERTEXAI",
                         "GOOGLE_API_KEY"])
        elif provider == "groq":
            keys.append("GROQ_API_KEY")
        elif provider == "huggingface":
            keys.append("HF_TOKEN")
        elif provider == "llama":
            keys.append("LLAMA_API_KEY")
        elif provider == "mistral":
            keys.append("MISTRAL_API_KEY")
        elif provider == "openai":
            keys.append("OPENAI_API_KEY")
            keys.append("OPENAI_BASE_URL")
        elif provider in ("opencode", "opencode-go"):
            keys.append("OPENCODE_API_KEY")
        elif provider == "xai":
            keys.append("XAI_API_KEY")
        elif provider == "openrouter":
            keys.append("OPENROUTER_API_KEY")
        elif provider is not None:
            raise ValueError(f"Unknown provider {provider}")

        for key in keys:
            if key in os.environ:
                env[key] = os.environ[key]

        env["OPENCODE_FAKE_VCS"] = "git"

        skills_cmd = self._build_register_skills_command()
        if skills_cmd:
            await self.exec_as_agent(environment, command=skills_cmd, env=env)

        mcp_cmd = self._build_register_config_command()
        if mcp_cmd:
            await self.exec_as_agent(environment, command=mcp_cmd, env=env)

        model_flag = f"--model={self.model_name} " if self.model_name else ""
        await self.exec_as_agent(
            environment,
            command=(
                ". ~/.nvm/nvm.sh; "
                f"opencode {model_flag}run --format=json --thinking "
                f"--dangerously-skip-permissions -- {escaped_instruction} "
                f"2>&1 </dev/null | stdbuf -oL tee /logs/agent/opencode.txt"
            ),
            env=env,
        )

    def _convert_events_to_trajectory(self, events):
        trajectory = super()._convert_events_to_trajectory(events)
        if not trajectory or not events:
            return trajectory
        step_idx = 0
        for event in events:
            if event.get("type") != "step_finish":
                continue
            part = event.get("part", {})
            tokens = part.get("tokens", {})
            if not tokens:
                continue
            if step_idx < len(trajectory.steps):
                step_idx += 1
        # Extract model names from tool_use metadata
        model_map: dict[int, str] = {}
        for event in events:
            if event.get("type") != "tool_use":
                continue
            meta = event.get("state", {}).get("metadata", {}) or {}
            model_info = meta.get("model", {}) or {}
            model_id = model_info.get("modelID", "") or ""
            if not model_id:
                continue
            ts = event.get("timestamp", 0)
            for idx, step in enumerate(trajectory.steps):
                if step.model_name == "?" or not step.model_name:
                    step.model_name = model_id
        return trajectory
