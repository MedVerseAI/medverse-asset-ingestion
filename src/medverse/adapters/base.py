"""Source adapter contract.  ALL source-specific logic lives inside adapters; the core never imports one directly."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from medverse.core.relations import RelationGraph
from medverse.selection.ontology import Ontology


class SourceAdapter(ABC):
    name = ""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.scfg = cfg["sources"][self.name]
        self.data_dir = Path(cfg["_runtime"]["data_dir"])
        self.entities: dict = {}                 # entity_id -> SourceEntity
        self.ontology = Ontology()
        self.relations = RelationGraph()
        self.problems: list = []

    def _dir(self, key: str, default: Path) -> Path:
        v = self.scfg.get(key, "")
        return Path(v).expanduser() if v else default

    @abstractmethod
    def discover(self) -> dict:
        """Cheap availability check: {'available': bool, 'files': [{path, sha256?}], 'problems': [...]}"""

    @abstractmethod
    def build(self) -> None:
        """Read metadata only (no geometry): fill entities / ontology / relations."""

    @abstractmethod
    def load(self, entity):
        """Load the entity's geometry as a BaseAsset (MeshAsset | VolumeAsset | PointCloudAsset)."""

    def validate_source(self) -> list:
        """Source-specific sanity checks run after load; returns a list of warning strings."""
        return []
