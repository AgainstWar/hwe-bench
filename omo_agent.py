import copy
import json
import os
import shlex
from pathlib import Path

from harbor.agents.installed.base import with_prompt_template
from harbor.agents.installed.opencode import OpenCode
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class OMOAgent(OpenCode):

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
                "bunx oh-my-openagent install --no-tui "
                "--claude=no --openai=no --gemini=no --copilot=no "
                "--opencode-zen=no --opencode-go=yes "
                "--zai-coding-plan=no --kimi-for-coding=no "
                "--vercel-ai-gateway=no --skip-auth"
            ),
        )

    def _build_register_config_command(self) -> str | None:
        config = {}
        existing = Path.home() / ".config" / "opencode" / "opencode.json"
        if existing.exists():
            try:
                config = json.loads(existing.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        if self.mcp_servers:
            mcp = {}
            for server in self.mcp_servers:
                if server.transport == "stdio":
                    cmd_list = [server.command] + server.args if server.command else []
                    mcp[server.name] = {"type": "local", "command": cmd_list}
                else:
                    mcp[server.name] = {"type": "remote", "url": server.url}
            config["mcp"] = mcp

        if self.model_name and "/" in self.model_name:
            provider, model_id = self.model_name.split("/", 1)
            provider_config = {"models": {model_id: {}}}
            base_url = os.environ.get("OPENAI_BASE_URL")
            if base_url and provider == "openai":
                provider_config.setdefault("options", {})["baseURL"] = base_url
            config["provider"] = {provider: provider_config}

        config = self._deep_merge(copy.deepcopy(self._DEFAULT_CONFIG), config)
        config = self._deep_merge(config, self._opencode_config)

        if not config:
            return None

        escaped = shlex.quote(json.dumps(config, indent=2))
        return f"mkdir -p ~/.config/opencode && echo {escaped} > ~/.config/opencode/opencode.json"

    def _convert_events_to_trajectory(self, events):
        trajectory = super()._convert_events_to_trajectory(events)
        if not trajectory or not events:
            return trajectory
        step_idx = 0
        for event in events:
            if event.get("type") != "step_finish":
                continue
            part = event.get("part") or {}
            model = part.get("model", "") or ""
            if not model:
                continue
            if step_idx < len(trajectory.steps):
                trajectory.steps[step_idx].model_name = model
                step_idx += 1
        return trajectory

    @with_prompt_template
    async def run(self, instruction: str, environment: BaseEnvironment,
                  context: AgentContext) -> None:
        escaped_instruction = shlex.quote(instruction)
        env = {}
        keys = []

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
                "bunx oh-my-openagent install --no-tui "
                "--claude=no --openai=no --gemini=no --copilot=no "
                "--opencode-zen=no --opencode-go=yes "
                "--zai-coding-plan=no --kimi-for-coding=no "
                "--vercel-ai-gateway=no --skip-auth"
            ),
        )

    def _build_register_config_command(self) -> str | None:
        """Preserve existing opencode.json (incl. omo plugin) and merge new config."""
        config: dict[str, Any] = {}

        existing = Path.home() / ".config" / "opencode" / "opencode.json"
        if existing.exists():
            try:
                config = json.loads(existing.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        if self.mcp_servers:
            mcp: dict[str, dict[str, Any]] = {}
            for server in self.mcp_servers:
                if server.transport == "stdio":
                    cmd_list = [server.command] + server.args if server.command else []
                    mcp[server.name] = {"type": "local", "command": cmd_list}
                else:
                    mcp[server.name] = {"type": "remote", "url": server.url}
            config["mcp"] = mcp

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

        config_json = json.dumps(config, indent=2)
        escaped = shlex.quote(config_json)
        return f"mkdir -p ~/.config/opencode && echo {escaped} > ~/.config/opencode/opencode.json"

    def _convert_events_to_trajectory(self, events):
        trajectory = super()._convert_events_to_trajectory(events)
        if not trajectory or not events:
            return trajectory

        step_idx = 0
        for event in events:
            if event.get("type") != "step_finish":
                continue
            part = event.get("part", {})
            model = part.get("model", "") or ""
            if not model:
                continue
            if step_idx < len(trajectory.steps):
                trajectory.steps[step_idx].model_name = model
                step_idx += 1

        return trajectory
