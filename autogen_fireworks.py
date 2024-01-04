# To install required packages:
# pip install pyautogen==0.2.2

import os

os.environ['OAI_CONFIG_LIST'] = """[{"model": "accounts/fireworks/models/qwen-72b-chat",
                                    "api_key": "<FIREWORKS_API_KEY>", 
                                    "base_url":"https://api.fireworks.ai/inference/v1"}]
                                """


import autogen

llm_config={
    "timeout": 600,
    "cache_seed": 25,  # change the seed for different trials
    "config_list": autogen.config_list_from_json(
        "OAI_CONFIG_LIST",
        filter_dict={"model": ["accounts/fireworks/models/qwen-72b-chat"]},
    ),
    "temperature": 0.2,
}

from autogen.agentchat.contrib.math_user_proxy_agent import MathUserProxyAgent

# create an AssistantAgent instance named "assistant"
assistant = autogen.AssistantAgent(
    name="assistant",
    llm_config=llm_config,
    is_termination_msg=lambda x: True if "TERMINATE" in x.get("content") else False,
)
# create a UserProxyAgent instance named "user_proxy"
mathproxyagent = MathUserProxyAgent(
    name="mathproxyagent",
    human_input_mode="NEVER",
    is_termination_msg=lambda x: True if "TERMINATE" in x.get("content") else False,
    code_execution_config={
        "work_dir": "work_dir",
        "use_docker": False,
    },

    max_consecutive_auto_reply=5,
)

task1 = """
Find all $x$ that satisfy the inequality $(2x+10)(x+3)<(3x+9)(x+8)$. """

mathproxyagent.initiate_chat(assistant, problem=task1)