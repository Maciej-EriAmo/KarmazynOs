# KarmazynOS — srodowisko w kontenerze
# Substrat DOMYSLNIE: native Rust (override: KARMAZYN_SUBSTRATE=python)
export PYTHONPATH="/opt/karmazyn:/opt/karmazyn/kernel:/opt/karmazyn/software:/opt/karmazyn/native${PYTHONPATH:+:$PYTHONPATH}"
export KARMAZYN_HOME="/opt/karmazyn/software"
export KARMAZYN_SUBSTRATE="${KARMAZYN_SUBSTRATE:-native}"
alias karmazyn='python3 /opt/karmazyn/software/karmazyn_boot.py'
