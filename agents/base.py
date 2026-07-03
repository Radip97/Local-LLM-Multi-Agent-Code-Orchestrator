import sys
import os
import base64
import mimetypes
from openai import OpenAI
import config

class BaseAgent:
    def __init__(self, role: str, model_name: str = None):
        self.role = role
        self.client = OpenAI(
            base_url=config.API_BASE_URL,
            api_key=config.API_KEY
        )
        self.model_name = model_name
        self._cached_model = None

    def get_model(self) -> str:
        """
        Returns the configured model name, or auto-detects one if set to None.
        """
        if self.model_name:
            return self.model_name
        
        if self._cached_model:
            return self._cached_model
            
        try:
            # Query local API to see loaded models
            models_response = self.client.models.list()
            # Filter out embedding models
            models = [m.id for m in models_response.data if "embed" not in m.id.lower()]
            if not models:
                raise Exception("No local LLM models found running at " + config.API_BASE_URL)
            
            # Smart mapping based on role
            if self.role == "Developer":
                # Prefer 7b coder or any coder
                coders = [m for m in models if "coder" in m.lower()]
                if coders:
                    # Pick first (which is 7b coder in our case)
                    self._cached_model = coders[0]
                else:
                    self._cached_model = models[0]
            elif self.role == "Planner":
                # Prefer 14b coder or any coder
                coders = [m for m in models if "coder" in m.lower()]
                # If multiple coders, pick the 14b coder, otherwise first
                if len(coders) > 1:
                    self._cached_model = next((c for c in coders if "14b" in c.lower()), coders[0])
                elif coders:
                    self._cached_model = coders[0]
                else:
                    self._cached_model = models[0]
            elif self.role == "QA":
                # Prefer general models (non-coders like qwen3.5 or gemma)
                non_coders = [m for m in models if "coder" not in m.lower()]
                if non_coders:
                    # Prefer gemma or qwen3.5
                    self._cached_model = next((n for n in non_coders if "gemma" in n.lower() or "3.5" in n.lower()), non_coders[0])
                else:
                    self._cached_model = models[0]
            else:
                self._cached_model = models[0]
                
            return self._cached_model
        except Exception as e:
            print(f"Error auto-detecting models from local API: {e}", file=sys.stderr)
            print("Please ensure LM Studio or Ollama is running and its server is active.", file=sys.stderr)
            sys.exit(1)

    @staticmethod
    def encode_images(image_paths: list[str]) -> list[dict]:
        """
        Encodes a list of image file paths into OpenAI-compatible multimodal
        content parts using base64 data URLs.
        Returns a list of image_url content dicts ready to be embedded in a message.
        """
        parts = []
        for path in image_paths:
            if not os.path.exists(path):
                print(f"[Warning] Image not found, skipping: {path}", file=sys.stderr)
                continue
            mime_type, _ = mimetypes.guess_type(path)
            if mime_type is None:
                # Default to jpeg if unknown
                ext = os.path.splitext(path)[1].lower()
                mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                            ".gif": "image/gif", ".webp": "image/webp"}
                mime_type = mime_map.get(ext, "image/jpeg")
            try:
                with open(path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{b64_data}"
                    }
                })
            except Exception as e:
                print(f"[Warning] Failed to encode image '{path}': {e}", file=sys.stderr)
        return parts

    def call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        """
        Utility method to call the local LLM using the OpenAI client.
        Text-only call. Use call_llm_with_images() for multimodal calls.
        """
        return self.call_llm_with_images(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            image_paths=[]
        )

    def call_llm_with_images(self, system_prompt: str, user_prompt: str,
                              temperature: float = 0.2, image_paths: list[str] = None) -> str:
        """
        Calls the LLM with optional image attachments.
        If image_paths is provided and non-empty, images are encoded as base64
        and embedded in the user message as multimodal content parts.
        Falls back to text-only if no images provided.
        """
        model = self.get_model()
        image_paths = image_paths or []

        # Build the user message content
        if image_paths:
            image_parts = self.encode_images(image_paths)
            if image_parts:
                # Multimodal message: text + images
                user_content = [
                    {"type": "text", "text": user_prompt},
                    *image_parts
                ]
            else:
                # All images failed to encode — fall back to text
                user_content = user_prompt
        else:
            user_content = user_prompt

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with LLM model '{model}': {e}")
