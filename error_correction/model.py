# model.py
import os
import requests
import re
from typing import List, Union, Dict
import json
from tenacity import (
    retry,
    stop_after_attempt,  # type: ignore
    wait_random_exponential,  # type: ignore
)
from transformers.generation.utils import GenerationMixin
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import InferenceClient
from openrouter import OpenRouter
import os
from config import api_key, hf_token

class ChatModel():
    def __init__(
        self,
        model_name: str = "gemini-3-flash-preview",
        max_tokens: int = 7409,
        temperature: float = 0.8,
        n: int = 1,
        local = False
    ):
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.n = n
        self.local = local
        self.api_key = api_key

        if local == True:
            self.model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype="auto", device_map="auto")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    @retry(wait=wait_random_exponential(min=1, max=60),stop=stop_after_attempt(6))
    def generate_remote(self, messages: List[Dict]) -> Union[List[str], str]:
        if "llama" in self.model_name.lower():
            prompt = "\n".join([m["content"] for m in messages])
            print("Llama prompt given: " + prompt)

            try:
                client = InferenceClient(api_key=hf_token)

                try:
                    completion = client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=min(self.max_tokens, 4096)
                    )
                    response_text = completion.choices[0].message.content
                except Exception:
                    response_text = client.text_generation(
                        model=self.model_name,
                        prompt=prompt,
                        max_new_tokens=min(self.max_tokens, 4096),
                        temperature=self.temperature
                    )

                print("Response generated:" + response_text)
                return response_text
            except Exception as e:
                raise RuntimeError(f"Llama API Error:\n{e}") from e

        headers = {
            "Content-Type": "application/json"
        }

        # convert messages -> gemini format
        prompt = "\n".join([m["content"] for m in messages])

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens
            }
        }

        print ("Gemini prompt given: "+prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            print("URL:", url)
            print("Response:", response.text)
            raise RuntimeError(
                f"Gemini API Error {response.status_code}:\n{response.text}"
            )

        response = response.json()
        print ("Response generated:" + response["candidates"][0]["content"]["parts"][0]["text"])
        return response["candidates"][0]["content"]["parts"][0]["text"]    




    def generate_local(self, messages: List[Dict]) -> Union[List[str], str]:
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        generated_ids = self.model.generate(
            **model_inputs,
            max_new_tokens=512,
            temperature = self.temperature,
            do_sample = True
        )
        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        response = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return response




    def generate(self, messages: List[Dict]) -> Union[List[str], str]:
        if self.local == True:
            return self.generate_local(messages)
        else:
            return self.generate_remote(messages) 


if __name__ == "__main__":
    system_prompt = """
You only complete chats with syntax correct Pyrtl code.
"""

    user_prompt = """
"""

    llm = ChatModel(
        model_name="gemini-2.5-flash",
        temperature=0.8,
        local=False
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    response = llm.generate(messages)
    print(response)




"""    
"""




"""    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
    def generate_remote(self, messages: List[Dict]) -> Union[List[str], str]:
        try:
            client = InferenceClient(provider="featherless-ai", api_key="HF_TOKEN")
            prompt = "\n".join([m["content"] for m in messages])
            completion = client.text_generation(
                model="meta-llama/Meta-Llama-3-70B",
                prompt=prompt,
                max_new_tokens=self.max_tokens,
                temperature=self.temperature
            )
            print (completion)
            return completion
        except Exception as e:
            print(f"HF ERROR: {e}")
            # Note: your function signature expects a string or list of strings, 
            # so returning a tuple ("unknown", "...") might cause issues later.
            return "LLM annotation failed."
"""




"""
    @retry(wait=wait_random_exponential(min=1, max=60),stop=stop_after_attempt(6))
    def generate_remote(self, messages: List[Dict]) -> Union[List[str], str]:

        headers = {
            "Content-Type": "application/json"
        }

        # convert messages -> gemini format
        prompt = "\n".join([m["content"] for m in messages])

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens
            }
        }

        print ("Gemini prompt given: "+prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key=GEMINI_KEY"
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            print("URL:", url)
            print("Response:", response.text)
            raise RuntimeError(
                f"Gemini API Error {response.status_code}:\n{response.text}"
            )

        response = response.json()
        print ("Response generated:" + response["candidates"][0]["content"]["parts"][0]["text"])
        return response["candidates"][0]["content"]["parts"][0]["text"]    



 try:
            client = InferenceClient(provider="featherless-ai", api_key="HF_TOKEN")
            prompt = "\n".join([m["content"] for m in messages])
            completion = client.text_generation(
                model="meta-llama/Meta-Llama-3-70B",
                prompt=prompt,
                max_new_tokens=self.max_tokens,
                temperature=self.temperature
            )
            print (completion)
            return completion
        except Exception as e:
            print(f"HF ERROR: {e}")
            # Note: your function signature expects a string or list of strings, 
            # so returning a tuple ("unknown", "...") might cause issues later.
            return "LLM annotation failed."





                        
    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
    def generate_remote(self, messages: List[Dict]) -> Union[List[str], str]:
        try:
            prompt = "\n".join([m["content"] for m in messages])

            with OpenRouter(
                api_key="OPENROUTER_KEY"
            ) as client:

                response = client.chat.send(
                    model="meta-llama/llama-3.3-70b-instruct:free",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )

                text = response.choices[0].message.content
                print(text)
                return text

        except Exception as e:
            import traceback
            print("OPENROUTER ERROR:", repr(e))
            traceback.print_exc()
            raise
"""
