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
                 omo_copilot="no", omo_opencode_zen="no", omo_opencode_go="no",
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
        await self.exec_as_agent(environment,
            command=(
                "cat > /tmp/override_omo.py << 'PYEOF'\n"
                "import json, os\n"
                "p = os.path.expanduser('~/.config/opencode/oh-my-openagent.json')\n"
                "if not os.path.exists(p): exit()\n"
                "c = json.load(open(p))\n"
                "for s in ('agents', 'categories'):\n"
                "    for n in c.get(s, {}):\n"
                "        c[s][n]['model'] = 'openai/gpt-5.4'\n"
                "        if 'variant' in c[s][n]:\n"
                "            c[s][n]['variant'] = 'xhigh'\n"
                "        for fb in c[s][n].get('fallback_models', []):\n"
                "            fb['model'] = 'openai/gpt-5.4'\n"
                "            if 'variant' in fb:\n"
                "                fb['variant'] = 'xhigh'\n"
                "json.dump(c, open(p, 'w'), indent=2)\n"
                "print('OMO models overridden: all agents use openai/gpt-5.4 xhigh')\n"
                "PYEOF\n"
                "python3 /tmp/override_omo.py && "
                "cp ~/.config/opencode/oh-my-openagent.json /logs/agent/oh-my-openagent.json 2>/dev/null"
            ),
        )

    def _build_register_config_command(self) -> str | None:
        api_key = os.environ.get("OPENAI_API_KEY") or ""
        base_url = os.environ.get("OPENAI_BASE_URL") or ""
        if not api_key or not base_url:
            return None

        config_json = json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "plugin": ["oh-my-openagent@latest"],
            "provider": {
                "openai": {
                    "options": {"baseURL": base_url, "apiKey": api_key},
                    "models": {
                        "gpt-5.2": {"name": "GPT-5.2", "limit": {"context": 400000, "output": 128000}, "options": {"store": False}, "variants": {"low": {}, "medium": {}, "high": {}, "xhigh": {}}},
                        "gpt-5.5": {"name": "GPT-5.5", "limit": {"context": 1050000, "output": 128000}, "options": {"store": False}, "variants": {"low": {}, "medium": {}, "high": {}, "xhigh": {}}},
                        "gpt-5.5-pro": {"name": "GPT-5.5 Pro", "limit": {"context": 1050000, "output": 128000}, "options": {"store": False}, "variants": {"low": {}, "medium": {}, "high": {}, "xhigh": {}}},
                        "gpt-5.4": {"name": "GPT-5.4", "limit": {"context": 1050000, "output": 128000}, "options": {"store": False}, "variants": {"low": {}, "medium": {}, "high": {}, "xhigh": {}}},
                        "gpt-5.4-mini": {"name": "GPT-5.4 Mini", "limit": {"context": 400000, "output": 128000}, "options": {"store": False}, "variants": {"low": {}, "medium": {}, "high": {}, "xhigh": {}}},
                        "gpt-5.3-codex-spark": {"name": "GPT-5.3 Codex Spark", "limit": {"context": 128000, "output": 32000}, "options": {"store": False}, "variants": {"low": {}, "medium": {}, "high": {}}},
                        "gpt-5.3-codex": {"name": "GPT-5.3 Codex", "limit": {"context": 400000, "output": 128000}, "options": {"store": False}, "variants": {"low": {}, "medium": {}, "high": {}, "xhigh": {}}},
                        "codex-mini-latest": {"name": "Codex Mini", "limit": {"context": 200000, "output": 100000}, "options": {"store": False}, "variants": {"low": {}, "medium": {}, "high": {}}},
                    },
                }
            },
            "agent": {
                "build": {"options": {"store": False}},
                "plan": {"options": {"store": False}},
            },
        })
        escaped = shlex.quote(config_json)
        return (
            f"mkdir -p ~/.config/opencode && "
            f"echo {escaped} > ~/.config/opencode/opencode.json && "
            f"cp ~/.config/opencode/opencode.json /logs/agent/opencode.json 2>/dev/null"
        )

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
        for event in events:
            if event.get("type") != "tool_use":
                continue
            part = event.get("part", {}) or {}
            meta = part.get("state", {}).get("metadata", {}) or {}
            model_info = meta.get("model", {}) or {}
            model_id = model_info.get("modelID", "") or ""
            if not model_id:
                continue
            name = f"{model_info.get('providerID', '')}/{model_id}"
            for step in trajectory.steps:
                if not step.model_name:
                    step.model_name = name
                    break
        return trajectory
