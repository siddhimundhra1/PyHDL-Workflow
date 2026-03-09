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
from config import *

class ChatModel():
    def __init__(
        self,
        model_name: str = "gemini-2.0-flash-exp",
        max_tokens: int = 2048,
        temperature: float = 0.4,
        n: int = 1,
        local = False
    ):
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.n = n
        self.local = local
        self.api_key = os.getenv("API_KEY")

        if local == True:
            self.model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype="auto", device_map="auto")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)


    @retry(wait=wait_random_exponential(min=1, max=60),stop=stop_after_attempt(6))
    def generate_remote(self, messages: List[Dict]) -> Union[List[str], str]:

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "n": self.n
        }

        response = requests.post(
            api_base,
            headers=headers,
            json=payload
        )

        # DEBUG SAFETY (prevents JSONDecodeError)
        if response.status_code != 200:
            raise RuntimeError(
                f"HF API Error {response.status_code}:\n{response.text}"
            )

        response = response.json()

        if self.n == 1:
            return response["choices"][0]["message"]["content"]

        return [
            choice["message"]["content"]
            for choice in response["choices"]
        ]


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
You only complete chats with syntax correct Verilog code. End the Verilog module code completion with 'endmodule'. Do not include module, input and output definitions.
"""

    user_prompt = """
"""

    llm = ChatModel(
        model_name="gemini-2.0-flash-exp",
        temperature=0.1,
        local=False
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    response = llm.generate(messages)
    print(response)
