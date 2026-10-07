"""Porchlight and beacon endpoint views.

The implementations remain imported from the compatibility module so existing
API imports continue to work while endpoint groups have stable module homes.
"""

from .views_legacy import (
    BeaconControlView,
    BeaconDetailView,
    BeaconListCreateView,
    GeocodeAddressView,
    NeighborhoodListView,
    PorchlightControlView,
    PorchlightDetailView,
    PorchlightListCreateView,
)

__all__ = [
    'BeaconControlView',
    'BeaconDetailView',
    'BeaconListCreateView',
    'GeocodeAddressView',
    'NeighborhoodListView',
    'PorchlightControlView',
    'PorchlightDetailView',
    'PorchlightListCreateView',
]