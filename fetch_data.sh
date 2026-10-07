#!/bin/bash
# Download the two BEIR collections used (SciFact, FiQA-2018) into data/.
cd "$(dirname "$0")/data"
for d in scifact fiqa; do
  curl -sSL -o $d.zip "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/$d.zip" && unzip -qo $d.zip
done
