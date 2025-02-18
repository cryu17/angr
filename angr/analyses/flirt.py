from typing import Union, List, Dict, TYPE_CHECKING, Optional
from functools import partial
from collections import defaultdict
import logging

import nampa
from archinfo.arch_arm import is_arm_arch

from ..analyses import AnalysesHub
from ..flirt import FlirtSignature, STRING_TO_LIBRARIES, LIBRARY_TO_SIGNATURES, FLIRT_SIGNATURES_BY_ARCH
from .analysis import Analysis

if TYPE_CHECKING:
    from angr.knowledge_plugins.functions import Function


_l = logging.getLogger(name=__name__)


MAX_UNIQUE_STRING_LEN = 70


class FlirtAnalysis(Analysis):
    """
    FlirtAnalysis accomplishes two purposes:

    - If a FLIRT signature file is specified, it will match the given signature file against the current binary and
      rename recognized functions accordingly.
    - If no FLIRT signature file is specified, it will use strings to determine possible libraries embedded in the
      current binary, and then match all possible signatures for the architecture.
    """
    def __init__(self, sig: Optional[Union[FlirtSignature,str]]=None):

        if sig:
            if isinstance(sig, str):
                # this is a file path
                sig = FlirtSignature(self.project.arch.name.lower(), self.project.simos.name.lower(), "Temporary",
                                          sig, None)

                self.signatures = [sig]

        else:
            if not FLIRT_SIGNATURES_BY_ARCH:
                raise RuntimeError("No FLIRT signatures exist. Please load FLIRT signatures by calling "
                                   "load_signatures() before running FlirtAnalysis.")

            # determine all signatures to match against strings in mapped memory regions
            mem_regions = [ self.project.loader.memory.load(seg.vaddr, seg.memsize)
                            for seg in self.project.loader.main_object.segments
                            if seg.filesize > 0 and seg.memsize > 0 ]

            self.signatures = list(self._find_hits_by_strings(mem_regions))
            _l.debug("Identified %d signatures to apply.", len(self.signatures))

        self._is_arm = is_arm_arch(self.project.arch)

        for sig_ in self.signatures:
            self._match_all_against_one_signature(sig_)

    def _find_hits_by_strings(self, regions: List[bytes]) -> List[FlirtSignature]:
        library_hits: Dict[str, int] = defaultdict(int)
        for s, libs in STRING_TO_LIBRARIES.items():
            for region in regions:
                if s.encode("ascii") in region:
                    for lib in libs:
                        library_hits[lib] += 1

        # sort libraries based on the number of hits
        sorted_libraries = sorted(library_hits.keys(), key=lambda lib: library_hits[lib], reverse=True)
        arch_lowercase = self.project.arch.name.lower()

        for lib in sorted_libraries:
            for sig in LIBRARY_TO_SIGNATURES[lib]:
                if sig.arch == arch_lowercase:
                    yield sig

    def _match_all_against_one_signature(self, sig: FlirtSignature):
        # match each function
        with open(sig.sig_path, "rb") as sigfile:
            flirt = nampa.parse_flirt_file(sigfile)
            for func in self.project.kb.functions.values():
                func: 'Function'
                if func.is_simprocedure or func.is_plt:
                    continue
                if not func.is_default_name:
                    # it already has a name. skip
                    continue

                start = func.addr
                if self._is_arm:
                    start = start & 0xffff_fffe

                max_block_addr = max(func.block_addrs_set)
                end_block = func.get_block(max_block_addr)
                end = max_block_addr + end_block.size

                if self._is_arm:
                    end = end & 0xffff_fffe

                # load all bytes
                func_bytes = self.project.loader.memory.load(start, end - start + 0x100)
                _callback = partial(self._on_func_matched, func)
                nampa.match_function(flirt, func_bytes, start, _callback)

    def _on_func_matched(self, func: 'Function', base_addr: int, flirt_func: 'nampa.FlirtFunction'):
        func_addr = base_addr + flirt_func.offset
        if func_addr != base_addr:
            # get the correct function
            func = None
            try:
                func = self.kb.functions.get_by_addr(func_addr)
            except KeyError:
                # the function is not found. Try the THUMB version
                if self._is_arm:
                    try:
                        func = self.kb.functions.get_by_addr(func_addr + 1)
                    except KeyError:
                        pass

            if func is None:
                _l.warning("FlirtAnalysis identified a function at %#x but it does not exist in function manager.",
                           func_addr)
                return

        if func.is_default_name:
            # set the function name
            # TODO: Make sure function names do not conflict with existing ones
            _l.debug("Identified %s @ %#x (%#x-%#x)", flirt_func.name, func_addr, base_addr, flirt_func.offset)
            if flirt_func.name != "?":
                func.name = flirt_func.name
            else:
                func.name = f"unknown_function_{func.addr:x}"
            func.is_default_name = False
            func.from_signature = "flirt"


AnalysesHub.register_default('Flirt', FlirtAnalysis)
