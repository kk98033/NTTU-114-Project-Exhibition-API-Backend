import os
import json
import requests
from bs4 import BeautifulSoup
import warnings

from dotenv import load_dotenv
import nltk
import nest_asyncio
from urllib3.exceptions import InsecureRequestWarning

from llama_index.core import (
    VectorStoreIndex, StorageContext, 
    load_index_from_storage, 
    SimpleDirectoryReader, 
    PromptTemplate,
    Settings
)
from llama_index.core.tools import QueryEngineTool, ToolMetadata, FunctionTool
from llama_index.core.query_engine import CitationQueryEngine, SubQuestionQueryEngine 
from llama_index.llms.ollama import Ollama
from llama_index.core.agent import ReActAgent
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.tools import FunctionTool

# load .env file
load_dotenv()

# get API key from .env file
os.environ["google_search_api_key"] = os.getenv('google_search_api_key')

# 忽略不安全的 SSL 警告
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

# TODO: 把 tool 獨立寫在另外一個檔案
"""
-------- Agent 可以使用的工具 --------
"""
def web_search(keyword: str) -> str:
    """根據給定的關鍵字進行網頁搜尋並返回搜尋結果的主要文字內容。(keyword 只能輸入中文)"""
    urls = get_search_url(keyword=keyword)
    print(urls)
    result = f'[根據以下文章內容，使用"**繁體中文**"整理有關於"{keyword}"的部分]:\n'
    for i, url in enumerate(urls):
        if not url.lower().endswith('.pdf'):
            result += f'文章{i+1}:\n"""'
            result += crawl_webpage(url) + '"""\n'
    print(len(result))
    return result

web_search_tool = FunctionTool.from_defaults(fn=web_search)
    
def get_search_url(keyword):
    url = f"https://www.googleapis.com/customsearch/v1?key={os.environ['google_search_api_key']}&cx=013036536707430787589:_pqjad5hr1a&q={keyword}&cr=countryTW&num=3"
    response = requests.get(url)
    if response.status_code == 200:
        search_results = response.json()
        links = [item['link'] for item in search_results.get('items', [])]
        return links
    else:
        print("Error occurred while fetching search results")
        return []

def crawl_webpage(url):
    try:
        response = requests.get(url, verify=False)  # Disabling SSL verification
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            main_content = soup.find("div", class_="main-content")
            if not main_content:
                main_content = soup

            for elem in main_content.find_all(["nav", "footer", "sidebar", "script", "noscript"]):
                elem.extract()

            lines = main_content.get_text().strip().splitlines()
            text_content = '\n'.join(line for line in lines if line.strip())
            return text_content
        else:
            print("Failed to fetch webpage")
            return ""
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return ""
"""
-------- [END] Agent 可以使用的工具 --------
"""

class ChatBot:
    def __init__(self):
        self.setup_settings()
        # self.load_dotenv_file() # TODO: 如果沒有影響就刪掉他
        self.prepare_environment()
        self.agent = self.configure_agent()
        self.response = None

    def setup_settings(self):
        Settings.embed_model = HuggingFaceEmbedding(model_name="intfloat/multilingual-e5-large-instruct")
        # Settings.embed_model = OpenAIEmbedding(embed_batch_size=10)

        # Settings.llm = Ollama(model="llama3.2:3b-instruct-fp16", request_timeout=60.0)
        # Settings.llm = Ollama(model="llama3.2:1b", request_timeout=60.0)
        Settings.llm = OpenAI(model="gpt-4o-mini-2024-07-18", stream=True, request_timeout=60.0)
        # Settings.llm = Ollama(model="llama3:instruct", request_timeout=60.0)
        # Settings.llm = OpenAI(model="gpt-3.5-turbo-instruct")
        # Settings.llm = Ollama(model="cwchang/llama3-taide-lx-8b-chat-alpha1", request_timeout=60.0)
        # Settings.llm = Ollama(model="ycchen/breeze-7b-instruct-v1_0:latest", request_timeout=60.0)
        # Settings.llm = Ollama(model="zephyr:7b", request_timeout=60.0)
        # Settings.llm = Ollama(model="openhermes:v2.5", request_timeout=60.0)

    def load_dotenv_file(self):
        load_dotenv()   

    def prepare_environment(self):
        # 獲取專案根目錄
        self.root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        print("專案根目錄是：", self.root_path)

        # 確認 storage 資料夾是否存在於專案根目錄
        storage_path = os.path.join(self.root_path, "storage")
        if os.path.exists(storage_path):
            print(f"'{storage_path}' 資料夾存在")
        else:
            print(f"'{storage_path}' 資料夾不存在")

    def configure_agent(self):
        path = "./storage/taiwanese"
        if not os.path.exists(path):
            print('storage does not exist!')
            # os.makedirs(path)
            tw_docs = SimpleDirectoryReader(
                input_files=["./pdfs/原住民資料.pdf", "./pdfs/原住民資料2.pdf"]
            ).load_data()

        # nttu_path = "./storage/nttu"
        # if not os.path.exists(nttu_path):
        #     nttu_docs = SimpleDirectoryReader(
        #         input_files=["./pdfs/台東大學介紹.pdf"]
        #     ).load_data()

        museum_path = "./storage/museum"
        if not os.path.exists(museum_path):
            print(f'storage {museum_path} does not exist!')
            museum_docs = SimpleDirectoryReader(
                input_files=["./pdfs/博物館物品.pdf"]
            ).load_data()

        try:
            storage_context = StorageContext.from_defaults(persist_dir=path)
            tw_index = load_index_from_storage(storage_context)

            # nttu_storage_context = StorageContext.from_defaults(persist_dir=nttu_path)
            # nttu_index = load_index_from_storage(nttu_storage_context)

            museum_storage_context = StorageContext.from_defaults(persist_dir=museum_path)
            museuem_index = load_index_from_storage(museum_storage_context)

            index_loaded = True
            print("Index loaded!")
        except:
            index_loaded = False
            print("Index not loaded!")
            if tw_docs:
                tw_index = VectorStoreIndex.from_documents(tw_docs)
                tw_index.storage_context.persist(persist_dir=path)
                index_loaded = True

            # if nttu_docs:
            #     nttu_index = VectorStoreIndex.from_documents(nttu_docs)
            #     nttu_index.storage_context.persist(persist_dir=nttu_path)
            #     index_loaded = True

            if museum_docs:
                museuem_index = VectorStoreIndex.from_documents(museum_docs)
                museuem_index.storage_context.persist(persist_dir=museum_path)
                index_loaded = True

        if index_loaded:
            tw_citation_engine = CitationQueryEngine.from_args(
                tw_index, similarity_top_k=3, citation_chunk_size=512)
            
            # nttu_citation_engine = CitationQueryEngine.from_args(
            #     nttu_index, similarity_top_k=3, citation_chunk_size=512)

            museum_citation_engine = CitationQueryEngine.from_args(
                museuem_index, similarity_top_k=4, citation_chunk_size=1024)

            # Load custom prompts for citation engine
            with open("core/promp_configs/query_engine_prompt_CN.json", "r", encoding="utf-8") as file:
                prompts_dict = json.load(file)
            custom_qa_prompt_str = prompts_dict.get("response_synthesizer:text_qa_template")['PromptTemplate']['template']
            custom_refine_prompt_str = prompts_dict.get("response_synthesizer:refine_template")['PromptTemplate']['template']
            tw_citation_engine.update_prompts(
                {
                    "response_synthesizer:text_qa_template": PromptTemplate(custom_qa_prompt_str),
                    "response_synthesizer:refine_template": PromptTemplate(custom_refine_prompt_str)
                }
            )

            citation_tool = QueryEngineTool(
                query_engine=tw_citation_engine,
                metadata=ToolMetadata(
                    name="Taiwanese_indigenous",
                    description="用於幫助回答有關台灣原住民的問題，遇到**原住民**、**部落**或者**XX族**相關問題一律要使用此工具。例如:台灣原住民有幾族?, 介紹'XX族', 任何有關於'原住民'、'XX族'、'族群'或者是'部落'的問題"
                )
            )

            # nttu_citation_tool = QueryEngineTool(
            #     query_engine=nttu_citation_engine,
            #     metadata=ToolMetadata(
            #         name="NTTU_tool",
            #         description="用於回答有關'台東大學', '東大','nttu'的問題。"
            #     )
            # )

            museum_citation_tool = QueryEngineTool(
                query_engine=museum_citation_engine,
                metadata=ToolMetadata(
                    name="Museum_tool",
                    description="用於回答有關'博物館'文物問題。例如:'編號AT003217-001是甚麼物品?','介紹人形木雕板...任何有關於'博物館'的問題"
                )
            )

            show_RAG_sources_tool = FunctionTool.from_defaults(fn=self.show_RAG_sources)

            # tools = [nttu_citation_tool, citation_tool, show_RAG_sources_tool, web_search_tool]
            tools = [museum_citation_tool, citation_tool, show_RAG_sources_tool, web_search_tool]
            agent = ReActAgent.from_tools(tools=tools, verbose=True, embed_model="local")

            # Load system prompts from file
            react_system_header_str = self.load_string_from_file('core/promp_configs/react_system_header_str_CN.txt')
            if react_system_header_str:
                react_system_prompt = PromptTemplate(react_system_header_str)
                agent.update_prompts({"agent_worker:system_prompt": react_system_prompt})
                print("System prompt updated successfully!")
            return agent
        else:
            raise Exception("Unable to load or create index. Check the configuration and data files.")

    def load_string_from_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except FileNotFoundError:
            raise Exception("檔案不存在！")
        except Exception as e:
            raise Exception("讀取檔案時發生錯誤：", e)

    def show_RAG_sources(self, *args, **kwargs) -> str:
        """
            ** 此函式不接受任何輸入參數。 **
            ** 當用戶想要取得資料來源，請使用他。 **
            用來輸出參考資料的來源。
        """
        try:
            print('=======SOURCE=======')
            for source in self.response.source_nodes:
                print(source.node.get_text())
            print('=======END-SOURCE=======')
        except:
            return "[告訴用戶:發生了錯誤!]"
        # return sources
        return "[告訴用戶:所有的資料來源皆已經輸出!]"

    def chat(self, input_text):
        # streaming response
        self.response = self.agent.stream_chat(input_text)
        return self.response
    
    def normal_chat(self, input_text):
        # not streaming
        self.response = self.agent.chat(input_text)
        return self.response


if __name__ == "__main__":
    bot = ChatBot()
    while True:
        user_input = input("User: ")
        if user_input.lower() == "exit":
            break
        elif user_input.lower() == "reset":
            bot = ChatBot()
            print("Chatbot has been reset.")
        else:
            # Streaming response
            # response = bot.chat(user_input)
            # for token in response.response_gen:
            #     print(token, end="", flush=True)
            # print()

            # not streaming
            response = bot.normal_chat(user_input)
            print("Agent:", response)
