# KarmazynOS — srodowisko w kontenerze
export PYTHONPATH="/opt/karmazyn/kernel:/opt/karmazyn/software${PYTHONPATH:+:$PYTHONPATH}"
export KARMAZYN_HOME="/opt/karmazyn/software"
alias karmazyn='python3 /opt/karmazyn/software/karmazyn_boot.py'
