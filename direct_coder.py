import sys
import os
import re
from openai import OpenAI
import config

def apply_search_replace(file_path: str, block_content: str) -> str:
    if not os.path.exists(file_path):
        clean = block_content
        clean = re.sub(r'<<<<<<< SEARCH\s*\n', '', clean)
        clean = re.sub(r'\n=======\s*\n', '', clean)
        clean = re.sub(r'\n>>>>>>> REPLACE', '', clean)
        return clean

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = r'<<<<<<< SEARCH\s*\n([\s\S]*?)\n=======\s*\n([\s\S]*?)\n>>>>>>> REPLACE'
    matches = re.findall(pattern, block_content)
    
    if not matches:
        return block_content

    for search, replace in matches:
        if search in content:
            content = content.replace(search, replace, 1)
        else:
            search_norm = search.replace('\r\n', '\n')
            content_norm = content.replace('\r\n', '\n')
            if search_norm in content_norm:
                content = content_norm.replace(search_norm, replace, 1)
            else:
                raise ValueError(f"Could not find SEARCH block in file {os.path.basename(file_path)}:\n{search}")
                
    return content

def main():
    if len(sys.argv) < 3:
        print("Usage: python direct_coder.py <file_path> <prompt>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    prompt = " ".join(sys.argv[2:])
    
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)
        
    with open(file_path, 'r', encoding='utf-8') as f:
        file_content = f.read()
        
    client = OpenAI(base_url=config.API_BASE_URL, api_key=config.API_KEY)
    
    system_prompt = """You are a senior software developer. Your task is to update an existing codebase file based on the user's prompt.
You MUST output your edits using SEARCH/REPLACE blocks.

Format:
<<<<<<< SEARCH
[exact lines from original file that you want to replace]
=======
[new replacement lines]
>>>>>>> REPLACE

Do NOT output markdown backticks. Just output the raw SEARCH/REPLACE blocks.
"""

    user_prompt = f"""File Path: {file_path}

Current Content:
{file_content}

Instructions:
{prompt}
"""

    print(f"Calling local LLM ({config.DEVELOPER_MODEL}) to edit {file_path}...")
    try:
        response = client.chat.completions.create(
            model=config.DEVELOPER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2
        )
        
        output = response.choices[0].message.content
        print("Response received. Applying changes...")
        
        updated_content = apply_search_replace(file_path, output)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
            
        print(f"Successfully updated file: {file_path}")
        
    except Exception as e:
        print(f"Error executing change: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
