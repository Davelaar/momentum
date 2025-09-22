
# Strict notional cap vs exchange rounding

This patch makes the risk wrappers *round-aware*:
- Fetches price tick and volume step per symbol from Kraken `AssetPairs`.
- Computes worst-case **effective_limit** (limit rounded **up** to price tick).
- Computes a single **qty** capped so `qty * effective_limit <= ENTRY_MAX_NOTIONAL`.
- Floors qty to the **coarsest** volume step across symbols.

This prevents rejections like `entry_max_notional_exceeded:10.15>10.00`
when the exchange rounds prices/volumes.

## Install
```
unzip /root/uploads/tick_safe_qty_patch.zip -d /root/uploads/_tick_safe_qty_patch
rsync -a /root/uploads/_tick_safe_qty_patch/momentum/ /var/www/vhosts/snapdiscounts.nl/momentum/momentum/
chown -R snapdiscounts:psacln /var/www/vhosts/snapdiscounts.nl/momentum
```
