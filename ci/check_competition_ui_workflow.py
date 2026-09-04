#!/usr/bin/env python3
from pathlib import Path
import sys
from lxml import etree
ROOT=Path(__file__).resolve().parents[1]
GUIDE=ROOT/"docs/COMPETITION_UI_WORKFLOW.md"
PATHS=(
("Federation","Setup","Seasons"),
("Federation","Setup","Competition Setup","Competition Templates"),
("Federation","Setup","Competition Setup","Season Competitions"),
("Federation","Competition Workflow","Create Competition"),
("Federation","Competition Workflow","Competition Overview"),
("Federation","Competition Workflow","Registration Desk"),
("Federation","Competition Workflow","Format Studio"),
("Federation","Competition Workflow","Calendar Planner"),
("Federation","Competition Workflow","Schedule Planner"),
("Federation","Competition Workflow","Schedule Review Queue"),
("Federation","Competition Workflow","Match-Day Control"),
("Federation","Planning","Advanced Records","Matches"),
("Federation","Publication","Approved Schedules"),
("Federation","Publication","Schedule Publications"),
("Federation","Publication","Standings"),
("Federation","Administration","Reporting","Operational Health"),
("Federation","Administration","Operational Job Health"),
)
def index():
 records={}
 for path in ROOT.glob("sports_federation_*/views/*.xml"):
  try:tree=etree.parse(str(path))
  except etree.XMLSyntaxError:continue
  module=path.parts[-3]
  for node in tree.xpath("//menuitem"):
   rid=node.get("id");xmlid=rid if "." in rid else f"{module}.{rid}"
   parent=node.get("parent","");parent=parent if not parent or "." in parent else f"{module}.{parent}"
   records[xmlid]={"name":node.get("name",""),"parent":parent}
 return records
def exists(records,labels):
 for xid,record in records.items():
  if record["name"]!=labels[-1]:continue
  names=[record["name"]];parent=record["parent"]
  while parent in records:
   record=records[parent];names.append(record["name"]);parent=record["parent"]
  if tuple(reversed(names))==labels:return True
 return False
def main():
 records=index();guide=GUIDE.read_text();errors=[]
 for labels in PATHS:
  rendered=" > ".join(labels)
  if not exists(records,labels):errors.append(f"menu path missing: {rendered}")
  if rendered not in guide:errors.append(f"guide path missing: {rendered}")
 if errors:
  print("Competition UI workflow contract failed:", file=sys.stderr)
  for error in errors:
   print(f"- {error}", file=sys.stderr)
  return 1
 print("Competition UI workflow menu paths passed.");return 0
if __name__=="__main__":raise SystemExit(main())
