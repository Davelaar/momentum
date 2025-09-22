#!/usr/bin/env python3
import io,sys,re,os
p = os.path.join(os.path.dirname(__file__), "..", "kraken", "rest_client.py")
p = os.path.abspath(p)
with open(p,"r",encoding="utf-8") as f:
    s = f.read()
if "def balances(" in s:
    print("Already has balances(); no change needed:", p)
    sys.exit(0)
# naive insert before last method or before 'altname_for_wsname'
anchor = "async def altname_for_wsname"
i = s.find(anchor)
if i < 0:
    # append at end
    ns = s.rstrip()+"

"+"""    async def balances(self) -> dict:
        """Return account balances by asset, e.g. {"ZUSD": "123.45", ...}"""
        return await self._post_private("Balance", {})
"""
else:
    head = s[:i]
    tail = s[i:]
    ns = head + """    async def balances(self) -> dict:
        """Return account balances by asset, e.g. {"ZUSD": "123.45", ...}"""
        return await self._post_private("Balance", {})

""" + tail
with open(p,"w",encoding="utf-8") as f:
    f.write(ns)
print("Patched:", p)