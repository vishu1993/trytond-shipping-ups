# -*- coding: utf-8 -*-
"""
    test_ups

    Test ups Integration

    :copyright: (c) 2014-2015 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
import os

from decimal import Decimal
from time import time
from datetime import datetime
from dateutil.relativedelta import relativedelta


import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction
from trytond.config import config
from trytond.error import UserError
config.set('database', 'path', '.')


class TestUPS(unittest.TestCase):
    """Test UPS Integration
    """

    def setUp(self):
        trytond.tests.test_tryton.install_module('shipping_ups')
        self.Address = POOL.get('party.address')
        self.Sale = POOL.get('sale.sale')
        self.SaleConfig = POOL.get('sale.configuration')
        self.UPSService = POOL.get('ups.service')
        self.Product = POOL.get('product.product')
        self.Uom = POOL.get('product.uom')
        self.Account = POOL.get('account.account')
        self.Category = POOL.get('product.category')
        self.Carrier = POOL.get('carrier')
        self.PartyConfiguration = POOL.get('party.configuration')
        self.Party = POOL.get('party.party')
        self.PartyContact = POOL.get('party.contact_mechanism')
        self.PaymentTerm = POOL.get('account.invoice.payment_term')
        self.Country = POOL.get('country.country')
        self.CountrySubdivision = POOL.get('country.subdivision')
        self.PartyAddress = POOL.get('party.address')
        self.StockLocation = POOL.get('stock.location')
        self.StockShipmentOut = POOL.get('stock.shipment.out')
        self.Currency = POOL.get('currency.currency')
        self.Company = POOL.get('company.company')
        self.IrAttachment = POOL.get('ir.attachment')
        self.User = POOL.get('res.user')
        self.Template = POOL.get('product.template')
        self.GenerateLabel = POOL.get('shipping.label', type="wizard")

        assert 'UPS_LICENSE_NO' in os.environ, \
            "UPS_LICENSE_NO not given. Hint:Use export UPS_LICENSE_NO=<number>"
        assert 'UPS_SHIPPER_NO' in os.environ, \
            "UPS_SHIPPER_NO not given. Hint:Use export UPS_SHIPPER_NO=<number>"
        assert 'UPS_USER_ID' in os.environ, \
            "UPS_USER_ID not given. Hint:Use export UPS_USER_ID=<user_id>"
        assert 'UPS_PASSWORD' in os.environ, \
            "UPS_PASSWORD not given. Hint:Use export UPS_PASSWORD=<password>"

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard"
        )

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _create_fiscal_year(self, date_=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        FiscalYear = POOL.get('account.fiscalyear')
        Sequence = POOL.get('ir.sequence')
        SequenceStrict = POOL.get('ir.sequence.strict')
        Company = POOL.get('company.company')

        if date_ is None:
            date_ = datetime.utcnow().date()

        if not company:
            company, = Company.search([], limit=1)

        invoice_sequence, = SequenceStrict.create([{
            'name': '%s' % date_.year,
            'code': 'account.invoice',
            'company': company
        }])
        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date_.year,
            'start_date': date_ + relativedelta(month=1, day=1),
            'end_date': date_ + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date_.year,
                'code': 'account.move',
                'company': company,
            }])[0],
            'out_invoice_sequence': invoice_sequence,
            'in_invoice_sequence': invoice_sequence,
            'out_credit_note_sequence': invoice_sequence,
            'in_credit_note_sequence': invoice_sequence,
        }])
        FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec

        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else None

    def _create_payment_term(self):
        """Create a simple payment term with all advance
        """
        PaymentTerm = POOL.get('account.invoice.payment_term')

        return PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

    def setup_defaults(self):
        """Method to setup defaults
        """
        # Create currency
        self.currency, = self.Currency.create([{
            'name': 'United Stated Dollar',
            'code': 'USD',
            'symbol': 'USD',
        }])
        self.Currency.create([{
            'name': 'Indian Rupee',
            'code': 'INR',
            'symbol': 'INR',
        }])

        country_us, = self.Country.create([{
            'name': 'United States',
            'code': 'US',
        }])

        subdivision_florida, = self.CountrySubdivision.create([{
            'name': 'Florida',
            'code': 'US-FL',
            'country': country_us.id,
            'type': 'state'
        }])

        subdivision_california, = self.CountrySubdivision.create([{
            'name': 'California',
            'code': 'US-CA',
            'country': country_us.id,
            'type': 'state'
        }])

        with Transaction().set_context(company=None):
            company_party, = self.Party.create([{
                'name': 'Test Party',
                'vat_number': '123456',
                'addresses': [('create', [{
                    'name': 'Amine Khechfe',
                    'street': '247 High Street',
                    'zip': '94301-1041',
                    'city': 'Palo Alto',
                    'country': country_us.id,
                    'subdivision': subdivision_california.id,
                }])]
            }])

        self.ups_service, = self.UPSService.create([{
            'name': 'Next Day Air',
            'code': '01',
        }])

        self.ups_service2, = self.UPSService.create([{
            'name': 'Second Next Day Air',
            'code': '02',
        }])

        self.SaleConfig.create([{
            'ups_service_type': self.ups_service.id,
        }])
        self.company, = self.Company.create([{
            'party': company_party.id,
            'currency': self.currency.id,
        }])
        self.PartyContact.create([{
            'type': 'phone',
            'value': '8005551212',
            'party': self.company.party.id
        }])

        self.User.write(
            [self.User(USER)], {
                'main_company': self.company.id,
                'company': self.company.id,
            }
        )

        CONTEXT.update(self.User.get_preferences(context_only=True))

        self._create_fiscal_year(company=self.company)
        self._create_coa_minimal(company=self.company)
        self.payment_term, = self._create_payment_term()

        account_revenue, = self.Account.search([
            ('kind', '=', 'revenue')
        ])

        # Create product category
        category, = self.Category.create([{
            'name': 'Test Category',
        }])

        uom_kg, = self.Uom.search([('symbol', '=', 'kg')])
        uom_cm, = self.Uom.search([('symbol', '=', 'cm')])
        uom_pound, = self.Uom.search([('symbol', '=', 'lb')])

        # Carrier Carrier Product
        carrier_product_template, = self.Template.create([{
            'name': 'Test Carrier Product',
            'category': category.id,
            'type': 'service',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'cost_price_method': 'fixed',
            'account_revenue': account_revenue.id,
            'products': [('create', self.Template.default_products())]
        }])

        carrier_product = carrier_product_template.products[0]

        # Create product
        template, = self.Template.create([{
            'name': 'Test Product',
            'category': category.id,
            'type': 'goods',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'account_revenue': account_revenue.id,
            'weight': .5,
            'weight_uom': uom_pound.id,
            'products': [('create', self.Template.default_products())]
        }])

        self.product = template.products[0]

        # Create party
        carrier_party, = self.Party.create([{
            'name': 'Test Party',
        }])

        # Create party
        carrier_party, = self.Party.create([{
            'name': 'Test Party',
        }])

        self.carrier, = self.Carrier.create([{
            'party': carrier_party.id,
            'carrier_product': carrier_product.id,
            'carrier_cost_method': 'ups',
            'ups_license_key': os.environ['UPS_LICENSE_NO'],
            'ups_user_id': os.environ['UPS_USER_ID'],
            'ups_password': os.environ['UPS_PASSWORD'],
            'ups_shipper_no': os.environ['UPS_SHIPPER_NO'],
            'ups_is_test': True,
            'ups_uom_system': '01',
            'currency': self.currency.id,
        }])

        self.PartyConfiguration.create([{
            'default_validation_carrier': self.carrier.id,
        }])

        self.sale_party, = self.Party.create([{
            'name': 'Test Sale Party',
            'vat_number': '123456',
            'addresses': [('create', [{
                'name': 'John Doe',
                'street': '250 NE 25th St',
                'zip': '33137',
                'city': 'Miami, Miami-Dade',
                'country': country_us.id,
                'subdivision': subdivision_florida.id,
            }])]
        }])
        self.PartyContact.create([{
            'type': 'phone',
            'value': '8005763279',
            'party': self.sale_party.id
        }])

    def create_sale(self, party):
        """
        Create and confirm sale order for party with default values.
        """
        with Transaction().set_context(company=self.company.id):

            # Create sale order
            sale, = self.Sale.create([{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': party.id,
                'invoice_address': party.addresses[0].id,
                'shipment_address': party.addresses[0].id,
                'carrier': self.carrier.id,
                'ups_service_type': self.ups_service.id,
                'ups_saturday_delivery': True,
                'lines': [
                    ('create', [{
                        'type': 'line',
                        'quantity': 1,
                        'product': self.product,
                        'unit_price': Decimal('10.00'),
                        'description': 'Test Description1',
                        'unit': self.product.template.default_uom,
                    }]),
                ]
            }])

            self.StockLocation.write([sale.warehouse], {
                'address': self.company.party.addresses[0].id,
            })

            # Confirm and process sale order
            self.assertEqual(len(sale.lines), 1)
            self.Sale.quote([sale])
            self.assertEqual(len(sale.lines), 2)
            self.Sale.confirm([sale])
            self.Sale.process([sale])

    def test_0010_generate_ups_labels(self):
        """Test case to generate UPS labels.
        """
        Package = POOL.get('stock.package')
        ModelData = POOL.get('ir.model.data')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()
            self.create_sale(self.sale_party)

            shipment, = self.StockShipmentOut.search([])
            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
            })

            # Before generating labels
            # There are no packages generated
            # And no attachment created for labels
            self.assertFalse(shipment.packages)
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(company=self.company.id):
                with self.assertRaises(UserError):
                    shipment.make_ups_labels()

                # Create a package
                type_id = ModelData.get_id(
                    "shipping", "shipment_package_type"
                )
                package, = Package.create([{
                    'shipment': '%s,%d' % (shipment.__name__, shipment.id),
                    'type': type_id,
                    'moves': [('add', shipment.outgoing_moves)],
                }])
                # Call method to generate labels.
                shipment.make_ups_labels()

            self.assertTrue(shipment.packages)
            # Check if by default 1 package was created
            self.assertEqual(len(shipment.packages), 1)
            self.assertTrue(shipment.packages[0].tracking_number)
            self.assertEqual(
                shipment.packages[0].moves, shipment.outgoing_moves)
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )

    def test_0012_generate_ups_labels_using_wizard(self):
        """
        Test case to generate UPS labels using wizard
        """
        Package = POOL.get('stock.package')
        ModelData = POOL.get('ir.model.data')

        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            # Create sale order
            party = self.sale_party
            sale, = self.Sale.create([{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': party.id,
                'invoice_address': party.addresses[0].id,
                'shipment_address': party.addresses[0].id,
                'carrier': self.carrier.id,
                'ups_service_type': self.ups_service2.id,
                'ups_saturday_delivery': True,
                'lines': [
                    ('create', [{
                        'type': 'line',
                        'quantity': 1,
                        'product': self.product,
                        'unit_price': Decimal('10.00'),
                        'description': 'Test Description1',
                        'unit': self.product.template.default_uom,
                    }, {
                        'type': 'line',
                        'quantity': 2,
                        'product': self.product,
                        'unit_price': Decimal('10.00'),
                        'description': 'Test Description1',
                        'unit': self.product.template.default_uom,
                    }]),
                ]
            }])

            self.StockLocation.write([sale.warehouse], {
                'address': self.company.party.addresses[0].id,
            })

            # Confirm and process sale order
            self.assertEqual(len(sale.lines), 2)
            self.Sale.quote([sale])
            self.assertEqual(len(sale.lines), 3)
            self.Sale.confirm([sale])
            self.Sale.process([sale])

            self.assertEqual(len(sale.shipments), 1)
            shipment = sale.shipments[0]
            self.assertEqual(len(shipment.outgoing_moves), 2)

            self.StockShipmentOut.write([shipment], {
                'code': str(int(time())),
            })
            type_id = ModelData.get_id(
                "shipping", "shipment_package_type"
            )

            package1, package2 = Package.create([{
                'shipment': '%s,%d' % (shipment.__name__, shipment.id),
                'type': type_id,
                'moves': [('add', [shipment.outgoing_moves[0]])],
            }, {
                'shipment': '%s,%d' % (shipment.__name__, shipment.id),
                'type': type_id,
                'moves': [('add', [shipment.outgoing_moves[1]])],
            }])

            # Before generating labels
            # There are no attachment created for labels
            attatchment = self.IrAttachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(
                company=self.company.id, active_id=shipment.id
            ):
                # Call method to generate labels.
                session_id, start_state, _ = self.GenerateLabel.create()

                generate_label = self.GenerateLabel(session_id)

                result = generate_label.default_start({})

                self.assertEqual(result['shipment'], shipment.id)
                self.assertEqual(result['carrier'], shipment.carrier.id)
                self.assertEqual(result['no_of_packages'], 2)

                generate_label.start.shipment = shipment.id
                generate_label.start.override_weight = 0
                generate_label.start.carrier = result['carrier']

                result = generate_label.default_ups_config({})

                self.assertEqual(
                    result['ups_service_type'], shipment.ups_service_type.id
                )
                self.assertEqual(
                    result['ups_package_type'], shipment.ups_package_type
                )
                self.assertEqual(
                    result['ups_saturday_delivery'], True
                )

                generate_label.ups_config.ups_service_type = self.ups_service2
                # Customer Supplied Package
                generate_label.ups_config.ups_package_type = '02'
                generate_label.ups_config.ups_saturday_delivery = False

                result = generate_label.default_generate({})

                self.assertEqual(
                    result['message'],
                    'Shipment labels have been generated via %s and saved as '
                    'attachments for the shipment' % (
                        shipment.carrier.carrier_cost_method.upper()
                    )
                )

            self.assertTrue(package1.tracking_number)
            self.assertTrue(package2.tracking_number)
            self.assertEqual(shipment.carrier, self.carrier)
            self.assertNotEqual(shipment.cost, Decimal('0'))
            self.assertEqual(shipment.cost_currency, self.currency)
            self.assertEqual(shipment.ups_service_type, self.ups_service2)
            self.assertEqual(shipment.ups_package_type, '02')
            self.assertEqual(shipment.ups_saturday_delivery, False)
            self.assertTrue(
                self.IrAttachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) == 2
            )

    def test_0025_ups_readonly(self):
        """
        Test that UPS service name and code fields are not editable
        only if they originate from XML.
        """
        ModelData = POOL.get('ir.model.data')
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()

            xml_record = self.UPSService(ModelData.get_id(
                'shipping_ups', 'shipping_method_01'
            ))

            for argument in [
                    {'name': 'None'},
                    {'code': '1234'}
            ]:
                self.assertRaises(
                    UserError, self.ups_service.write,
                    [xml_record], argument
                )
            self.assertTrue(xml_record.system_generated)

            # Write on a record created manually is successful
            self.UPSService.write([self.ups_service], {
                'name': 'Test Service',
                'code': '5432',
            })
            self.assertFalse(self.ups_service.system_generated)

    def test_0030_address_validation(self):
        """
        Test address validation with ups
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()

            country_us, = self.Country.search([('code', '=', 'US')])

            subdivision_florida, = self.CountrySubdivision.search(
                [('code', '=', 'US-FL')]
            )
            subdivision_california, = self.CountrySubdivision.search(
                [('code', '=', 'US-CA')]
            )

            # Correct Address
            suggestions = self.Address(**{
                'name': 'John Doe',
                'street': '250 NE 25th St',
                'streetbis': '',
                'zip': '33141',
                'city': 'Miami',
                'country': country_us.id,
                'subdivision': subdivision_florida.id,
            }).validate_address()
            self.assertEqual(suggestions, True)

            # Wrong subdivision
            suggestions = self.Address(**{
                'name': 'John Doe',
                'street': '250 NE 25th St',
                'streetbis': '',
                'zip': '33141',
                'city': 'Miami',
                'country': country_us.id,
                'subdivision': subdivision_california.id,
            }).validate_address()
            self.assertTrue(len(suggestions) > 0)
            self.assertEqual(suggestions[0].subdivision, subdivision_florida)

            # Wrong city and subdivision
            suggestions = self.Address(**{
                'name': 'John Doe',
                'street': '250 NE 25th St',
                'streetbis': '',
                'zip': '33141',
                'city': '',
                'country': country_us.id,
                'subdivision': subdivision_california.id,
            }).validate_address()
            self.assertTrue(len(suggestions) > 1)
            self.assertEqual(suggestions[0].subdivision, subdivision_florida)

    def test_0035_ups_shipping_rates(self):
        """
        Tests the get_ups_shipping_rates() method.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()

            with Transaction().set_context(company=self.company.id):
                # Create sale order
                sale, = self.Sale.create([{
                    'reference': 'S-1001',
                    'payment_term': self.payment_term,
                    'party': self.sale_party.id,
                    'invoice_address': self.sale_party.addresses[0].id,
                    'shipment_address': self.sale_party.addresses[0].id,
                    'carrier': self.carrier.id,
                    'ups_service_type': self.ups_service.id,
                    'ups_saturday_delivery': True,
                    'lines': [
                        ('create', [{
                            'type': 'line',
                            'quantity': 1,
                            'product': self.product,
                            'unit_price': Decimal('10.00'),
                            'description': 'Test Description1',
                            'unit': self.product.template.default_uom,
                        }]),
                    ]
                }])

                self.StockLocation.write([sale.warehouse], {
                    'address': self.company.party.addresses[0].id,
                })
                self.assertEqual(len(sale.lines), 1)

            with Transaction().set_context(sale=sale):
                self.assertGreater(self.carrier.get_rates(), 0)


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.account.tests import test_account
    for test in test_account.suite():
        if test not in suite:
            suite.addTest(test)
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestUPS)
    )
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
