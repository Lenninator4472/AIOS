"""
AI-DOS Kernel: LLM Backend Abstraction
Talks to Ollama (local) or Groq (cloud), with pattern for more backends.
"""

import json
import os
import re
import sys
import requests
from typing import Optional, Generator


class LLMBackend:
    """Abstract base for LLM backends."""

    def query(self, system_prompt: str, user_input: str, history: list[dict]) -> str:
        raise NotImplementedError


class OllamaBackend(LLMBackend):
    """Local Ollama backend. No API keys, no cloud calls."""

    def __init__(self, model: str = "llama3.2:1b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def _build_payload(self, messages: list[dict], stream: bool = False) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "format": "json",
            "options": {
                "num_predict": 256,
                "num_ctx": 2048,
                "num_thread": 2,
            },
        }

    def _build_messages(self, system_prompt: str, user_input: str, history: list[dict]) -> list[dict]:
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_input})
        return messages

    def query(self, system_prompt: str, user_input: str, history: list[dict]) -> str:
        messages = self._build_messages(system_prompt, user_input, history)
        payload = self._build_payload(messages, stream=False)

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except requests.exceptions.ConnectionError:
            return json.dumps({
                "thought_process": "Kernel error: cannot reach LLM backend",
                "required_tools": [],
                "commands": [],
                "user_response": "☠ KERNEL PANIC: Cannot reach Ollama. Is it running? (`ollama serve`)",
            })
        except Exception as e:
            return json.dumps({
                "thought_process": f"Kernel error: {str(e)}",
                "required_tools": [],
                "commands": [],
                "user_response": f"☠ KERNEL ERROR: {str(e)}",
            })

    def query_stream(self, system_prompt: str, user_input: str, history: list[dict]) -> Generator[str, None, str]:
        """
        Streaming query. Yields content tokens as they arrive from Ollama.
        Returns the full accumulated response string after iteration completes.

        Usage:
            gen = llm.query_stream(system_prompt, user_input, history)
            for token in gen:
                print(token, end='', flush=True)
            full_response = gen.send(None)  # or simply consume all

        On error, yields the error JSON string as a single item.
        """
        messages = self._build_messages(system_prompt, user_input, history)
        payload = self._build_payload(messages, stream=True)
        full_response = ""

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    full_response += content
                    yield content
                if chunk.get("done"):
                    break

            return full_response

        except requests.exceptions.ConnectionError as e:
            err = json.dumps({
                "thought_process": "Kernel error: cannot reach LLM backend",
                "required_tools": [],
                "commands": [],
                "user_response": "☠ KERNEL PANIC: Cannot reach Ollama. Is it running? (`ollama serve`)",
            })
            yield err
            return err
        except Exception as e:
            err = json.dumps({
                "thought_process": f"Kernel error: {str(e)}",
                "required_tools": [],
                "commands": [],
                "user_response": f"☠ KERNEL ERROR: {str(e)}",
            })
            yield err
            return err


class GroqBackend(LLMBackend):
    """Cloud Groq backend. Requires GROQ_API_KEY env var."""

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.api_key = os.environ.get("GROQ_API_KEY", "")

    def _build_messages(self, system_prompt: str, user_input: str, history: list[dict]) -> list[dict]:
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_input})
        return messages

    def query(self, system_prompt: str, user_input: str, history: list[dict]) -> str:
        if not self.api_key:
            return json.dumps({
                "thought_process": "Kernel error: GROQ_API_KEY not set",
                "required_tools": [],
                "commands": [],
                "user_response": "☠ KERNEL ERROR: GROQ_API_KEY environment variable not set.",
            })
        messages = self._build_messages(system_prompt, user_input, history)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
        }
        try:
            resp = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except requests.exceptions.HTTPError as e:
            return json.dumps({
                "thought_process": f"Groq API error: {e}",
                "required_tools": [],
                "commands": [],
                "user_response": f"☠ GROQ ERROR: {e}",
            })
        except requests.exceptions.ConnectionError:
            return json.dumps({
                "thought_process": "Kernel error: cannot reach Groq API",
                "required_tools": [],
                "commands": [],
                "user_response": "☠ KERNEL PANIC: Cannot reach Groq API. Check internet connection.",
            })
        except Exception as e:
            return json.dumps({
                "thought_process": f"Kernel error: {str(e)}",
                "required_tools": [],
                "commands": [],
                "user_response": f"☠ KERNEL ERROR: {str(e)}",
            })

    def query_stream(self, system_prompt: str, user_input: str, history: list[dict]) -> Generator[str, None, str]:
        if not self.api_key:
            err = json.dumps({
                "thought_process": "Kernel error: GROQ_API_KEY not set",
                "required_tools": [],
                "commands": [],
                "user_response": "☠ KERNEL ERROR: GROQ_API_KEY not set.",
            })
            yield err
            return err
        messages = self._build_messages(system_prompt, user_input, history)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1024,
            "stream": True,
        }
        full_response = ""
        try:
            resp = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                stream=True,
                timeout=60,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    chunk_data = decoded[6:]
                    if chunk_data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_data)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            full_response += content
                            yield content
                    except json.JSONDecodeError:
                        continue
            return full_response
        except requests.exceptions.ConnectionError:
            err = json.dumps({
                "thought_process": "Kernel error: cannot reach Groq API",
                "required_tools": [],
                "commands": [],
                "user_response": "☠ KERNEL PANIC: Cannot reach Groq API.",
            })
            yield err
            return err
        except Exception as e:
            err = json.dumps({
                "thought_process": f"Kernel error: {str(e)}",
                "required_tools": [],
                "commands": [],
                "user_response": f"☠ KERNEL ERROR: {str(e)}",
            })
            yield err
            return err


def get_provider(model: str = "llama3.2:1b") -> LLMBackend:
    """Auto-detect: Groq if GROQ_API_KEY is set, else Ollama."""
    if os.environ.get("GROQ_API_KEY"):
        return GroqBackend()
    return OllamaBackend(model=model)


def extract_json(text: str) -> Optional[dict]:
    """
    Extract a JSON object from LLM response text.
    Handles nested braces, truncated output, code blocks, whitespace noise.
    """
    text = text.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    start = text.find("{")
    if start == -1:
        return None

    candidate = text[start:]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # If truncated (no closing brace), try appending closing braces
    if not candidate.endswith("}"):
        for depth in range(1, 6):
            try:
                return json.loads(candidate + "}" * depth)
            except json.JSONDecodeError:
                continue

    end = candidate.rfind("}")
    if end != -1:
        try:
            return json.loads(candidate[: end + 1])
        except json.JSONDecodeError:
            pass

    return None
