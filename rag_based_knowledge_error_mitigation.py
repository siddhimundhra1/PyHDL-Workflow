# rag_based_knowledge_error_mitigation.py
from code_rag.search import hybrid_search
from utils import extract_module_header, parse_code_block
from model import ChatModel

system_prompt = """
You are an expert in PyRTL-based hardware design.

You will be given:
1. One or more reference PyRTL design examples
2. A user's design specification

Your task is to generate a complete PyRTL implementation that uses the reference examples
as guidance for structure, style, and implementation patterns.

Instructions:
- Carefully study the reference examples from start to finish.
- Learn their coding patterns, including wire declarations, registers,
  combinational logic, sequential logic, control flow, and naming style.
- Reuse useful structural patterns when relevant to the user's request.
- Adapt the logic to satisfy the new specification rather than copying unrelated behavior.
- If multiple examples are provided, combine the most relevant patterns consistently.

Requirements:
- Fully satisfy all functionality described in the user's specification.
- Input/output names, bitwidths, and interfaces must match the user's specification exactly.
- Generate complete, correct, executable, and synthesizable PyRTL code.
- Include all required imports and signal declarations.
- Preserve clarity and clean coding style.

Output Rules:
- Return ONLY code.
- Do NOT include explanations, comments outside the code, or markdown text.
- Output a single Python code block containing valid PyRTL code.

CRITICAL: Always output a COMPLETE PyRTL design including:
- All Input() and Output() declarations
- All Register() and WireVector() declarations  
- All combinational and sequential logic
- All output assignments
The design must be immediately executable with `pyrtl.simulate()`. DO NOT TRUNCATE CODE OR RETURN PARTIA CODE.
"""

def rag_based_knowledge_error_mitigation(llm: ChatModel, description: str):
    examples = hybrid_search(description)

    example_prompt = "### Example Begin ###\n"
    for example in examples:
        example_prompt += f"{example}\n"
    example_prompt += "### Example End ###"

    user_prompt = (
    f"{example_prompt}\n"
    f"[Design Description]:\n{description}\n\n"
    f"Now write a complete PyRTL implementation for the above description:\n"
)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    response = llm.generate(messages)

    design = parse_code_block(response, "python")
    #print (user_prompt)
    #print("Code generated: ")
    #print (response)
    return design, example_prompt


if __name__ == "__main__":
    input_path = "./input"

    llm = ChatModel(model_name="gemini-3-flash-preview", temperature=0.1, local=False)

    with open(f"{input_path}/description.txt", "r", encoding='utf-8', errors='ignore') as file:
        description = file.read()

    with open(f"{input_path}/ref.sv", "r", encoding='utf-8', errors='ignore') as file:
        ref = file.read()

    with open(f"{input_path}/testbench.sv", "r", encoding='utf-8', errors='ignore') as file:
        testbench = file.read()

    corrected_design, example_prompt = rag_based_knowledge_error_mitigation(llm, description)

    with open(f"{input_path}/design.sv", "w", encoding='utf-8', errors='ignore') as file:
        file.write(corrected_design)

    #print(corrected_design)
    #print(example_prompt)
