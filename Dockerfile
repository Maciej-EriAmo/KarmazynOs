# KarmazynOS — obraz z separacja JADRO <-> OPROGRAMOWANIE.
#
# Trzy poziomy separacji, ktore daje ten obraz:
#   1. LOGICZNY  — brama strażnika w buildzie (ponizej): obraz NIE zbuduje sie,
#                  jesli plik jadra importuje oprogramowanie.
#   2. PLIKOWY   — jadro w warstwie read-only (root:root 0555); aplikacja jako
#                  non-root (USER magos) NIE moze nadpisac kodu jadra.
#   Poziom 3 (PROCESOWY: jadro jako osobny demon/kontener) wymaga protokolu IPC
#   i zmienia model z pamieci dzielonej na RPC — to osobna decyzja, nie ten obraz.

# ---- Stage 1: STRAŻNIK GRANICY (twarda brama buildu) ----
FROM alpine:3.20 AS guard
RUN apk add --no-cache python3
WORKDIR /src
COPY kernel_boundary.py ./
COPY kernel/   ./kernel/
COPY software/ ./software/
# exit 1 => build pada. Jadro importujace oprogramowanie sie NIE zbuduje.
RUN python3 kernel_boundary.py kernel/ software/

# ---- Stage 2: RUNTIME ----
FROM alpine:3.20
RUN apk add --no-cache python3 && adduser -D -u 1000 magos

# JADRO: read-only, wlasnosc root. Oprogramowanie (non-root) nie nadpisze kodu.
COPY --chown=root:root kernel/    /opt/karmazyn/kernel/
RUN chmod -R 0555 /opt/karmazyn/kernel
# OPROGRAMOWANIE: osobna warstwa.
COPY --chown=magos:magos software/ /opt/karmazyn/software/

COPY bin/karmazyn               /usr/local/bin/karmazyn
COPY etc/profile.d/karmazyn.sh  /etc/profile.d/karmazyn.sh
RUN chmod 0555 /usr/local/bin/karmazyn

ENV PYTHONPATH=/opt/karmazyn/kernel:/opt/karmazyn/software
ENV KARMAZYN_HOME=/opt/karmazyn/software
WORKDIR /home/magos
USER magos            # KLUCZOWE: read-only jadra bije tylko dla non-root
CMD ["/bin/sh", "-l"]
