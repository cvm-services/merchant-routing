import os, sys
sys.path.insert(0, os.path.expanduser("~/.hermes/bot/scripts"))
import routstr_delist as rd
print("type passed:", type("AB").__name__)
print("payload:", rd.relist_payload("AB"))
print("list('AB') ->", list("AB"))
