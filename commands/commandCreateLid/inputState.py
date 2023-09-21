from typing import Dict
from dataclasses import dataclass

@dataclass
class InputState:
    groups: Dict[str, bool]
    baseWidth: float
    baseLength: float
    heightUnit: float
    xyTolerance: float
    binWidth: float
    binLength: float
    binHeight: float
    hasBody: bool
    binBodyType: str
    binWallThickness: float
    hasLip: bool
    hasLipNotches: bool
    hasBase: bool
    hasBaseScrewHole: bool
    baseScrewHoleSize: float
    hasBaseMagnetSockets: bool
    baseMagnetSocketSize: float
    baseMagnetSocketDepth: float
    preserveChanges: bool

    def getGroupExpandedState(self, id: str):
      if id in self.groups:
        return self.groups[id]
      else:
        return True