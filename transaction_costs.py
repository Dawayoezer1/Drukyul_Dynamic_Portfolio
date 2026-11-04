"""Dated local-currency fee rules. No market-wide percentage fallback."""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import numpy as np
import pandas as pd

COMPONENTS = ('commission', 'regulatory', 'exchange_fee', 'tax', 'fx_cost', 'slippage')


def rounded(value, quantum=0.01, ceiling=False):
    q = Decimal(str(quantum))
    if q <= 0:
        raise ValueError('Rounding quantum must be positive.')
    return float((Decimal(str(value)) / q).quantize(
        Decimal('1'), rounding=ROUND_CEILING if ceiling else ROUND_HALF_UP) * q)


class Costs:
    def __init__(self, profiles, allow_snapshot=False, spread_bps=5.0, fx_bps=2.0):
        if not np.isfinite([spread_bps, fx_bps]).all() or min(spread_bps, fx_bps) < 0:
            raise ValueError('Estimated costs cannot be negative.')
        self.profiles, self.allow_snapshot = profiles, allow_snapshot
        self.spread_bps, self.fx_bps = spread_bps, fx_bps

    def profile(self, asset, date):
        matches = [p for p in self.profiles if
                   asset['route'] in ([p['route']] if isinstance(p['route'], str) else p['route'])
                   and p['currency'] == asset['currency']
                   and asset['asset_type'] in p['asset_types']]
        valid = [p for p in matches if p['from'] <= str(pd.Timestamp(date).date()) <= p['to']]
        if len(valid) == 1:
            return valid[0], 'dated profile'
        if not valid and self.allow_snapshot and len(matches) == 1:
            return matches[0], 'snapshot applied outside verified dates: assumption'
        raise ValueError(f"Need one dated fee profile for {asset['id']} on {date}; "
                         'configure fees.json or explicitly enable snapshot assumptions.')

    def trade(self, asset, date, delta_base, price_local, fx_rate, base_currency):
        if not np.isfinite([delta_base, price_local, fx_rate]).all() or min(price_local, fx_rate) <= 0:
            raise ValueError('Invalid trade inputs.')
        p, status = self.profile(asset, date)
        side = 'BUY' if delta_base > 0 else 'SELL'
        value = abs(delta_base) / fx_rate
        quantity = value / price_local
        local = {k: 0.0 for k in COMPONENTS}
        for rule in p['rules']:
            if rule.get('side', 'BOTH') not in ('BOTH', side):
                continue
            component = rule['component']
            if component not in COMPONENTS:
                raise ValueError('Unknown fee component.')
            amount = (rule.get('value_rate', 0) * value +
                      rule.get('share_rate', 0) * quantity + rule.get('fixed', 0))
            amount = max(amount, rule.get('minimum', 0))
            if 'cap_rate' in rule:
                amount = min(amount, rule['cap_rate'] * value)
            if 'cap_amount' in rule:
                amount = min(amount, rule['cap_amount'])
            # GST/VAT bases may explicitly include prior commission/regulatory/exchange fees.
            amount += rule.get('fee_tax_rate', 0) * sum(
                local[k] for k in rule.get('fee_tax_components', []))
            if amount < 0 or not np.isfinite(amount):
                raise ValueError('Invalid configured fee rule.')
            local[component] += rounded(amount, rule.get('quantum', 0.01),
                                         rule.get('ceiling', False))
        local['slippage'] += value * self.spread_bps / 10000
        if asset['currency'] != base_currency:
            local['fx_cost'] += value * self.fx_bps / 10000
        result = {k: v * fx_rate for k, v in local.items()}
        total = sum(result.values())
        return dict(date=pd.Timestamp(date), ticker=asset['ticker'], id=asset['id'],
                    exchange=asset['exchange'], country=asset['country'],
                    currency=asset['currency'], side=side, quantity=quantity,
                    price_local=price_local, fx_rate=fx_rate, gross_local=value,
                    gross_base=abs(delta_base), **result, total_cost=total,
                    net_cash_impact=-delta_base - total, profile=p['name'],
                    fee_status=status, fee_notes=p.get('notes', ''),
                    pricing='Raw close; fractional equivalents; estimated spread charged separately')
