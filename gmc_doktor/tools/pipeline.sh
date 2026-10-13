#!/usr/bin/env bash
# Lead pipeline: Common Crawl sample -> DNS (Shopify IPs) -> homepage confirm -> GMC-Doktor batch check.
set -u
cd /c/Users/anton
G="C:/Users/anton/AppData/Roaming/Claude/scratch-workspaces/d5e1b5d0-5889-43c4-bee8-f3311211cd16/629b46df-4fc1-46f2-9b78-b9acbd366717/scratch-2026-09-25-6dca1e/ecommerence/gmc_doktor"
PY=/c/Users/anton/AppData/Local/Temp/rtv/Scripts/python.exe
export PYTHONIOENCODING=utf-8 PYTHONPATH="$G"
$PY "$G/tools/collect_leads.py" cc --pages ${PAGES:-45} --seed ${SEED:-99} --out "$G/data/cc_all.txt"
$PY "$G/tools/collect_leads.py" dns --inp "$G/data/cc_all.txt" --out "$G/data/dns_shopify.txt"
grep "	shopify	" "$G/data/dns_shopify.txt" | cut -f1 | grep -v "^en\." | sort -u > "$G/data/shopify_candidates.txt"
$PY "$G/tools/collect_leads.py" detect --inp "$G/data/shopify_candidates.txt" --out "$G/data/shopify_dk.txt"
grep "	shopify	" "$G/data/shopify_dk.txt" | cut -f1 | sort -u > "$G/data/to_check.txt"
echo "to check: $(wc -l < "$G/data/to_check.txt")"
$PY -m gmcdoktor batch "$G/data/to_check.txt" --out "$G/data/batch"
echo PIPELINE_DONE
