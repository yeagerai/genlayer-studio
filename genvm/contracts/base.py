import os
import sys
import time
import asyncio
import json
import functools
import inspect

from genvm.contracts import llms
from genvm.utils import transaction_files, get_webpage_content

from dotenv import load_dotenv
load_dotenv()

def gas_model_logic():
    return 1

def serialize(obj):
    exclude_attrs = [
        'mode',
        'gas_used',
        'non_det_counter',
        'non_det_inputs',
        'non_det_outputs',
        'eq_principles_outs',
        'node_config'
    ]

    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    elif isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        return {k: serialize(v) for k, v in obj.__dict__.items() if not k.startswith('_') and k not in exclude_attrs}
    else:
        raise TypeError(f"Type {type(obj)} not serializable")

def icontract(cls):
    class WrappedClass(cls):
        def __init__(self, *args, **kwargs):
            self.node_config = json.load(open(os.environ.get('GENVMCONLOC') + '/node-config.json'))
            self.mode = None
            self.gas_used = 0
            self.non_det_counter = 0
            self.non_det_inputs = {}
            self.non_det_outputs = {}
            self.eq_principles_outs = {}
            self.qw_similarity_scale = "between 1 to 10 (where 1 = 'not at all similar' and 10 = 'identical')"
            self.qw_similarity_success = [7, 8, 9, 10]
            super(WrappedClass, self).__init__(*args, **kwargs)

        async def query_webpage(self, url:str, prompt:str):

            _, _, _, recipt_file = transaction_files()

            llm_function = self.get_llm_function()

            if self.node_config['type'] == 'leader':
                self.mode = 'leader'
                url_body = get_webpage_content(url)
                submitted_prompt = f"Complete the following task:\n\nTask:\n{prompt}'\n\nUsing the following text:\n\nText:\n{url_body}"
                leader_response = await llm_function(self.node_config, submitted_prompt, None, None)
                self.non_det_outputs[self.non_det_counter]['input'] = {'prompt': prompt, 'url': url}
                self.non_det_outputs[self.non_det_counter]['output'] = leader_response
                self.non_det_counter+=1
                return leader_response
            elif self.node_config['type'] == 'validator':
                self.mode = 'validator'
                # make sure the leader file exists first
                if not os.path.exists(recipt_file):
                    raise Exception(recipt_file + ' does not exist!')
                # get the leader file
                file = open(recipt_file, 'r')
                leader_recipt = json.load(file)
                file.close()
                # get the webpage
                url_body = get_webpage_content(url)
                submitted_prompt = f"Complete the following task:\n\nTask:\n{prompt}'\n\nUsing the following text:\n\nText:\n{url_body}"
                wq_response = await llm_function(self.node_config, submitted_prompt, None, None)
                self.non_det_outputs[self.non_det_counter]['input'] = {'prompt': prompt, 'url': url, 'leader_recipt': leader_recipt}
                self.non_det_outputs[self.non_det_counter]['output'] = wq_response

                leader_output = leader_recipt['result']['non_det_outputs']['0']['output']
                # Compaire to the leaders
                eq_prompt = f"Using a scale {self.qw_similarity_scale} tell me how similar the follow two blocks of text are.\n\nText 1:\n{leader_output}\n\nText 2:\n{wq_response}\n\nRespond using the following JSON format:\n{'similarity': a value from the scale,'reason': the reason for the lack of similarity (if there is any)}"
                similarity_response = await llm_function(self.node_config, eq_prompt, None, None)

                is_similar = False
                if self.qw_similarity_success in similarity_response['similarity']:
                    is_similar = True
                self.eq_principles_outs[self.non_det_counter] = similarity_response
                self.eq_principles_outs[self.non_det_counter]['is_similar'] = is_similar
                self.non_det_counter+=1
                if not is_similar:
                    # 'call_llm' < 'wrapped_function' <'ask_for_coin' < 'wrapped_function' < 'main' < ...
                    #                                  --------------
                    method_name = inspect.stack()[2].function
                    self._write_receipt(self, method_name, {})
                    print('There was limited similarity between the validators output and the leaders output.', file=sys.stderr)
                    sys.exit(1)
                return leader_output
            else:
                raise ValueError("Invalid mode.")

        async def call_llm(self, prompt:str, consensus_eq:str=None):

            _, _, _, recipt_file = transaction_files()

            leader_recipt = None
            if self.node_config['type'] == 'validator' and os.path.exists(recipt_file):
                file = open(recipt_file, 'r')
                leader_recipt = json.load(file)
                file.close()

            llm_function = self.get_llm_function()

            self.non_det_inputs[self.non_det_counter] = {}
            self.non_det_inputs[self.non_det_counter]["input"] = prompt
            if self.node_config['type'] == 'leader':
                self.mode = 'leader'
                final_response = await llm_function(self.node_config, prompt, None, None)
                self.non_det_outputs[self.non_det_counter] = {}
                self.non_det_outputs[self.non_det_counter]["output"] = final_response
                self.non_det_counter+=1
                return final_response
            
            elif self.node_config['type'] == 'validator' and consensus_eq and leader_recipt:
                validator_response = await llm_function(self.node_config, prompt, None, None)
                self.non_det_outputs[self.non_det_counter] = {}
                self.non_det_outputs[self.non_det_counter]["output"] = validator_response

                leader_output = leader_recipt['result']['non_det_outputs']['0']['output']

                eq_prompt = f"Given the equivalence principle '{consensus_eq}', decide whether the following two outputs can be considered equivalent.\nOutput 1: {leader_output}\nOutput 2: {validator_response}\nRespond with: TRUE or FALSE"
                validation_response = await llm_function(self.node_config, eq_prompt, None, None)

                agreement = True if validation_response.strip().upper() == "TRUE" else False
                self.eq_principles_outs[self.non_det_counter] = {
                    "response": validation_response,
                    "agrees_with_leader": agreement
                }
                self.non_det_counter+=1
                if not agreement:
                    # 'call_llm' < 'wrapped_function' <'ask_for_coin' < 'wrapped_function' < 'main' < ...
                    #                                  --------------
                    method_name = inspect.stack()[2].function
                    self._write_receipt(self, method_name, {})
                    print('The validator did not agree with the leader.', file=sys.stderr)
                    sys.exit(1)
                return leader_output

            else:
                raise ValueError("Invalid mode or missing parameters for validator.")

        # This will get excuited under the following TWO conditiions:
        # 1. When the method on the class has finished
        # 2. When a validator disagrees with the leaders outcome
        def _write_receipt(self, method_name, args):
            receipt = {
                "class": self.__class__.__name__,
                "method": method_name,
                "args":args,
                "gas_used": self.gas_used,
                "mode": self.mode,
                "contract_state": serialize(self),
                "node_config": self.node_config,
                "non_det_inputs": self.non_det_inputs,
                "non_det_outputs": self.non_det_outputs,
                "eq_principles_outs": self.eq_principles_outs
            }

            with open(os.environ.get('GENVMCONLOC') + '/receipt.json', 'w') as file:
                json.dump(receipt, file, indent=4)

        def __getattribute__(self, name):
            orig_attr = super().__getattribute__(name)
            if callable(orig_attr) and not name.startswith("_"):
                @functools.wraps(orig_attr)
                async def wrapped_function(*args, **kwargs):
                    self.gas_used = gas_model_logic()

                    if asyncio.iscoroutinefunction(orig_attr):
                        output = await orig_attr(*args, **kwargs)
                    else:
                        output = orig_attr(*args, **kwargs)
                    
                    self._write_receipt(name, args)
                    print("Execution Finished!")

                    return output
                return wrapped_function
            else:
                return orig_attr
        

        def get_llm_function(self):
            llm_function = getattr(llms, 'call_ollama')
            if self.node_config['provider'] == 'openai':
                llm_function = getattr(llms, 'call_openai')
            return llm_function

    return WrappedClass
