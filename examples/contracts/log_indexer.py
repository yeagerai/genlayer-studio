# {
#   "Seq": [
#     { "Depends": "py-lib-genlayermodelwrappers:test" },
#     { "Depends": "py-genlayer:test" }
#   ]
# }

from genlayer import *
import genlayermodelwrappers
import numpy as np
from dataclasses import dataclass


@dataclass
class StoreValue:
    log_id: u256
    text: str


# contract class
@gl.contract
class LogIndexer:
    vector_store: VecDB[np.float32, typing.Literal[384], StoreValue]

    def __init__(self):
        pass

    def get_emb_generator(self):
        return genlayermodelwrappers.SentenceTransformer("all-MiniLM-L6-v2")

    def get_emb(
        self, txt: str
    ) -> np.ndarray[tuple[typing.Literal[384]], np.dtypes.Float32DType]:
        return self.get_emb_generator()(txt)

    @gl.public.view
    def get_closest_vector(self, text: str) -> dict | None:
        emb = self.get_emb(text)
        result = list(self.vector_store.knn(emb, 1))
        if len(result) == 0:
            return None
        result = result[0]
        return {
            "vector": list(str(x) for x in result.key),
            "similarity": str(1 - result.distance),
            "id": result.value.log_id,
            "text": result.value.text,
        }

    @gl.public.write
    def add_log(self, log: str, log_id: int) -> None:
        emb = self.get_emb(log)
        self.vector_store.insert(emb, StoreValue(text=log, log_id=u256(log_id)))

    @gl.public.write
    def update_log(self, log_id: int, log: str) -> None:
        emb = self.get_emb(log)
        for elem in self.vector_store.knn(emb, 2):
            if elem.value.text == log:
                elem.value.log_id = u256(log_id)

    @gl.public.write
    def remove_log(self, id: int) -> None:
        for el in self.vector_store:
            if el.value.log_id == id:
                el.remove()
