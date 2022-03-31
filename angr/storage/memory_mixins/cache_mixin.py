from . import MemoryMixin
from cachesim import CacheSimulator, Cache

class CacheMixin(MemoryMixin):
    def __init__(self, levels=1, sets=[512], ways=[8], sizes=[64], policies=["LRU"], **kwargs):
        super().__init__(**kwargs)
        
        mem = MainMemory()
        prev = None
        for l in range(levels):
            if prev:
                c = Cache("L" + str(levels - l), sets[l], ways[l], sizes[l], policies[l], store_to=prev, load_from=prev)
                prev = c
            else:
                c = Cache("L" + str(levels - l), sets[l], ways[l], sizes[l], policies[l])
                prev = c
                mem.load_to(c)
                mem.load_from(c)
        
        self.cache = CacheSimulator(prev, mem)

    def load(self, addr: int, size: int=None, , **kwargs):
        super().load(addr, size=size, **kwargs)
        self.cache.load(addr, length=size)

    def store(self, addr: int, data, size: int=None, **kwargs):
        super().store(addr, size=size, **kwargs)
        self.cache.store(addr, length=size)
        # need to change pycachesim to support actual data
        # need to be able to reveal cache information
    
    def copy(self, memo):
        o = super().copy(memo)
        o.cache = self.cache
        return o

    def merge(self, others, merge_conditions, common_ancestor=None):
        pass #needs to be implemented
        return True