# -*- coding: utf-8 -*-
"""
    __init__.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool
from party import Address
from carrier import Carrier, UPSService, CarrierConfig
from sale import Configuration, Sale
from stock import (
    ShipmentOut, StockMove, ShippingUps, GenerateShippingLabel
)
from configuration import UPSConfiguration


def register():
    Pool.register(
        Address,
        Carrier,
        CarrierConfig,
        UPSService,
        UPSConfiguration,
        Configuration,
        Sale,
        StockMove,
        ShipmentOut,
        ShippingUps,
        module='ups', type_='model'
    )

    Pool.register(
        GenerateShippingLabel,
        module='ups', type_='wizard'
    )
