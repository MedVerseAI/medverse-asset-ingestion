"""
integration_config.py
---------------------
Thin config module for the integration pipeline (integration_geometry.py / integration_data.py /
integrate_brainnetome_bodyparts3d.py).

It no longer defines its own paths, settings or Log class: everything comes from
    anat_config   -> paths (inputs in data/, outputs in outputs/) + all REG_* / BN_* / scene settings
    anat_classes  -> the ONE shared `log`, `WARNINGS`, `warn`, `reset_state`

Importing with  `from integration_config import *`  gives the other integration modules
all of these names plus os / re / json / math / collections / numpy.
"""
import os
import re
import json
import math
import collections
import numpy as np

from anat_config import *                                   # noqa: F401,F403
from anat_classes import log, WARNINGS, warn, reset_state   # noqa: F401