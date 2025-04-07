"""
基于脚本的任务型对话系统
在任意地方加重听节点
"""
import  json
import  pandas as pd
import re
import os
class  DailogueSystem:
    def __init__(self):
        self.load()
    def load(self):
        self.nodes_info = {}
        self.load_scenario("scenario-买衣服.json")#场景文件
        self.load_slot("slot_fitting_templet.xlsx")#槽位文件
        # 初始化一个专门的节点用于实现在任意时刻的重听
        self.init_repeat_node()
  # 实现思路：一个重听节点可以是所有节点的子节点
    def init_repeat_node(self):
        node_id = "special_repeat_node"
        node_info = {"id": node_id, "intent": ["再说一遍"]}
        self.nodes_info[node_id] = node_info  # 记录这个新节点
        for node_info in self.nodes_info.values():  # 成为每个已有节点的子节点
            node_info["childnode"] = node_info.get("childnode", []) + [node_id]



    def load_scenario(self,scenario_file):
        with open(scenario_file,"r",encoding="utf-8") as f:
            self.scenario = json.load(f)
        scenario_name = os.path.basename(scenario_file).split(".")[0]
        for node in self.scenario:
            node_id = node["id"]
            self.nodes_info[scenario_name + node["id"]] = node
            if "childnode" in node:
                node["childnode"] = [scenario_name + child_node for child_node in node["childnode"]]
            self.nodes_info[node_id] = node
    def load_slot(self,slot_file):
        self.slot_templet = pd.read_excel(slot_file)
        #slot qurey values
        self.slot_to_qv = {}
        for i,row in self.slot_templet.iterrows():
            slot = row["slot"]
            query = row["query"]
            values = row["values"]
            self.slot_to_qv[slot] = [query,values]
    def intent_recognition(self,memory):
        #意图识别模块，跟available_nodes中每个节点打分，选择分数最高的作为当前节点
        max_score = -1
        for node_name in memory["available_nodes"]:
            node_info = self.nodes_info[node_name]
            score = self.get_node_score(node_info,memory["query"])
            if score > max_score:
                max_score = score
                memory["current_node"] = node_name
        return memory
    def get_node_score(self,node_info,memory):
        #跟node中的intent算分
        intent = node_info["intent"]
        score = 0
        for intent_item in intent:
            score = max(score, self.sentence_match_score(intent_item,memory))
        return score
    def sentence_match_score(self,string1,string2):
        #计算两个句子间的相似度，用jarrcard距离
        s1 = set(string1)
        s2 = set(string2)
        return len(s1 & s2) / len(s1 | s2)
    def slot_filling(self,memory):
        #槽位填充模块，根据当前节点中的slot，去memory中找对应的query，然后去slot_to_qv中找对应的values，最后根据values去memory中找对应的slot
        #根据命中的节点，获取对应的slot
        slot_list = self.nodes_info[memory["current_node"]].get("slot", [])
        #对qurey进行槽位填充
        for slot in slot_list:
            values = self.slot_to_qv[slot][1]
            if re.search(values,memory["query"]):
                memory[slot] = re.search(values,memory["query"]).group()
        return memory

        pass
    def nlu(self,memory):
        memory = self.intent_recognition(memory)
        memory = self.slot_filling(memory)
        return memory
    def dst(self,memory):
        #确认当前hit_node所需要的所有槽位是否已经齐全
        slot_list = self.nodes_info[memory["current_node"]].get("slot", [])
        for slot in slot_list:
            if slot not in memory:
                memory["require_slot"] = slot
                return memory
        memory["require_slot"] = None
        if memory["current_node"] == "special_repeat_node" :
            memory["state"] = "repeat"
        else:
            memory["state"] =  None
        return memory
    def pm(self,memory):
        if memory['require_slot'] is not None:
            #反问策略
            memory["available_nodes"] = [memory["current_node"]]
            memory["policy"] = "ask"
        elif memory["state"] == "repeat":
            #重听策略，不对memory做修改，只更新policy
            memory['policy'] = "repeat"
        else:
            memory["available_nodes"] = self.nodes_info[memory["current_node"]].get("childnode", [])
            memory['policy'] = "answer"
        return  memory


    def dpo(self,memory):
        #如果require_slot为空，则执行当前节点的操作，否则进行反问
        if memory["require_slot"] is None:
            memory["policy"] = "reply"
            #子节点是否开放
            childnodes = self.nodes_info[memory["current_node"]].get("childnode",[])
            memory["available_nodes"] = childnodes
        else:
            memory["policy"] = "ask"
            memory["available_nodes"] = [memory["current_node"]]
        return memory
        # 执行动作 很多事可以做
    def nlg(self,memory):
        # 自然语言生成
        if memory["policy"] == "ask":
            slot = memory["require_slot"]
            reply = self.slot_to_qv[slot][0] # 反问文本，来自xlsx
        elif memory["policy"] == "repeat":
            # 使用上一轮的回复
            reply = memory["reply"]
        else:
            reply = self.nodes_info[memory["current_node"]]["response"]
            reply = self.replace_templet(reply, memory)
        memory["reply"] = reply
        return memory
    def fill_in_template(self,response,memory):
        slot_list = self.nodes_info[memory["current_node"]].get("slot", [])
        for slot in slot_list:
            if slot in response:
                response = response.replace(slot,memory[slot])
        return response
    def get_response(self,query,memory):

        memory["query"] = query
        memory = self.nlu(memory)
        memory = self.dst(memory) #dialoge state tracking
        memory = self.pm(memory) # dialogue policy optimization
        memory = self.nlg(memory)
        return memory
    def replace_templet(self, reply, memory):
        # 替换模板中的槽位
        hit_node = memory["current_node"]
        for slot in self.nodes_info[hit_node].get("slot", []):
            reply = re.sub(slot, memory[slot], reply)
        return reply




if __name__ == '__main__':
    ds = DailogueSystem()
    memory = {"available_nodes":["scenario-买衣服node1"]} #默认初始记忆为空
    # print(ds.slot_to_qv)

    while True:
        # query = "你好我想定一张北京到上海的机票"
        query = input("User：")
        memory =  ds.get_response(query,memory)
        print(memory)
        print("System:", memory["reply"])




