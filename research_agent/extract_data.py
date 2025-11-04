import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

MODEL_NAME = "pmo-gpt-4.1-nano"


chat_client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)


def llm_extract(source:str) -> str:
    """Use LLM to extract relevant information from source text."""
    prompt = f"""Extract the key information from the following text for analysis:

    {source}

    Provide a concise summary highlighting the main points.
    """
    response = chat_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "You are an expert data extraction tool. \
                                           you will extract original content,its data and source date from the provided source."},
            {"role": "user", "content": prompt}
        ],
   
    )

    token_usage = {
        'prompt_tokens': response.usage.prompt_tokens,
        'completion_tokens': response.usage.completion_tokens,
        'total_tokens': response.usage.total_tokens
    }

    return response.choices[0].message.content.strip(), token_usage


with open("/Users/andrew_lim/Documents/_code/LADP_projects/PMO/TI-tool-main/crawled_data/thinkgeoenergy/64-of-66-parcels-sold-in-blm-nevada-geothermal-lease-sale.md", "r", encoding="utf-8") as f:
    content = f.read()


text, token_usage = llm_extract(content)
print(text)
print(token_usage)