from genvm.base.equivalence_principle import EquivalencePrinciple


class A:

    def __init__(self) -> None:
        self.name = "dave"

    async def method1(self):
        final_result = {}
        async with EquivalencePrinciple(
            result=final_result,
            principle="The result['give_coin'] has to be exactly the same",
        ) as eq:
            result = await eq.call_llm("something")
            self.name = "james"
            eq.set(result)
        age = 38
        return final_result["output"]
