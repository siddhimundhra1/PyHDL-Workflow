from model import ChatModel
from rule_based_description_refinement import rule_based_description_refinement
from rag_based_knowledge_error_mitigation import rag_based_knowledge_error_mitigation
import time
import os
from config import model_name

if __name__ == "__main__":

    task_prompt = "You only complete chats with syntax correct PyRTL code.\n"
    input_path = "./input"
    description_path = f"{input_path}/original_description.txt"
    if not os.path.exists(description_path):
        description_path = f"{input_path}/description.txt"
    descriptions_dir = f"{input_path}/descriptions"

    llm = ChatModel(model_name=model_name, temperature=0.8, local=False)

    if os.path.isdir(descriptions_dir):
        description_files = sorted(
            os.path.join(descriptions_dir, filename)
            for filename in os.listdir(descriptions_dir)
            if filename.endswith(".txt")
        )
    else:
        description_files = [description_path]

    for description_file in description_files:
        with open(description_file, "r", encoding='utf-8', errors='ignore') as file:
            description = file.read()

        output_name = os.path.splitext(os.path.basename(description_file))[0].replace("_prompt", "")
        output_dir = f"{input_path}/output/{output_name}"
        os.makedirs(output_dir, exist_ok=True)

        for i in range(1, 21):
            idx = f"{i:02d}"  # 01, 02, ..., 20

            # Baseline: no rules or RAG
            # messages = [{"role": "user", "content": task_prompt + "\n" + description}]
            # response = llm.generate(messages)
            #with open(f"{input_path}/no_rules_or_rag_{idx}.py", "w", encoding='utf-8', errors='ignore') as file:
            #    file.write(response)

            # Stage 1: rule-based description refinement
            design, refined_description = rule_based_description_refinement(llm, description, task_prompt)
            #with open(f"{input_path}/description_{idx}.txt", "w", encoding='utf-8', errors='ignore') as file:
            #    file.write(refined_description)

            # Stage 2: RAG-based generation on refined description
            corrected_design, example_prompt = rag_based_knowledge_error_mitigation(llm, refined_description)
            # corrected_design, example_prompt = rag_based_knowledge_error_mitigation(llm, description)

            with open(f"{output_dir}/{output_name}_sample{idx}.py", "w", encoding='utf-8', errors='ignore') as file:
                file.write(corrected_design)
                # file.write(design)
            time.sleep(10)
