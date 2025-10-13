import asyncio
import json
from search import clarify_and_search
from learning_pts import get_learning

if __name__ == "__main__":
    topic = "What is the expected growth rate of chinese tuition market in Singapore?"
    
    file_name = "Chinese_tuition"
    asyncio.run(clarify_and_search(topic, file_name))

    asyncio.run(get_learning(file_path=file_name, file_name=file_name))
