#!/usr/bin/env python3
"""
thermal_invaders.py — Thermal Invaders v2.9
============================================
- Pełna integracja z bąblem KarmazynOS
- Automatyczne czyszczenie atomów (brak śmieci)
- Maksymalny poziom (10), wygrana
- Punkty za bossa
- Limit pocisków
- Wyjście: F1
"""

import time
import numpy as np
from typing import List, Tuple, Optional

try:
    import pygame
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False

HAS_KARMAZYN = False
try:
    from karmazyn_display import DrawCtx
    from karmazyn_atom import Atom
    HAS_KARMAZYN = True
except ImportError:
    class Atom:
        def __init__(self, aid, S, E, T):
            self.id = aid
            self.S = np.array(S, dtype=np.float32)
            self.E = E
            self.T = T
            self.state = "COLD"
        def heat(self, v): self.T = min(100, self.T + v)
        def cool(self, v): self.T = max(0, self.T - v)


# ====================== STAŁE ======================
PHI_DIM = 15
PLAYER_WIDTH, PLAYER_HEIGHT = 30, 20
PLAYER_SPEED = 420.0
BULLET_SIZE, BULLET_SPEED = 6, -650.0
MAX_BULLETS = 12                     # limit pocisków gracza
MAX_LEVEL = 10                       # gra kończy się po 10 poziomach

ENEMY_WIDTH, ENEMY_HEIGHT = 28, 24
ENEMY_BASE_SPEED = 62.0
ENEMY_DROP_STEP = 18

PLAYER_SHOOT_DELAY = 0.22
ENEMY_SHOOT_DELAY = 1.1

LIVES = 3
SCORE_PER_KILL = 10
BOSS_SCORE = 150                     # punkty za bossa
ENEMY_HEAT_RATE = 8.5
COOLING_PER_HIT = 26.0

C_PLAYER = (100, 230, 100)
C_BULLET = (255, 255, 90)
C_ENEMY_COLD = (40, 80, 140)
C_ENEMY_WARM = (80, 170, 255)
C_ENEMY_HOT = (255, 90, 40)
C_BOSS = (200, 30, 30)
C_EXPLOSION = (255, 180, 30)
C_POWERUP = (255, 240, 60)
C_BG = (12, 12, 22)
C_UI = (230, 230, 230)
C_FROZEN = (100, 200, 255)


class Enemy:
    def __init__(self, x, y, idx, runtime, reset_id=0, is_boss=False):
        self.x, self.y = x, y
        self.idx = idx
        self.is_boss = is_boss
        self.speed_x = ENEMY_BASE_SPEED
        self.shoot_cooldown = ENEMY_SHOOT_DELAY
        self.last_shot = 0.0
        self.frozen_until = 0.0
        self.health = 220 if is_boss else 100

        vec = np.random.randn(PHI_DIM).astype(np.float32)
        vec[0] = x / 100.0
        vec[1] = y / 100.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        unique_id = f"invader_{reset_id}_{idx}"
        if HAS_KARMAZYN and runtime:
            if runtime.has_atom(unique_id):
                runtime.delete_atom(unique_id)
            self.atom = runtime.create_atom(unique_id, vec, f"{x},{y}", 40.0)
        else:
            self.atom = Atom(unique_id, vec, f"{x},{y}", 40.0)

    def heat(self, amount):
        if self.atom:
            self.atom.T = min(100.0, self.atom.T + amount)

    def cool(self, amount):
        if self.atom:
            self.atom.T = max(0.0, self.atom.T - amount)
        self.health -= amount

    def freeze(self, duration=3.0):
        self.frozen_until = time.monotonic() + duration

    @property
    def T(self):
        return self.atom.T if self.atom else 0.0

    @property
    def state(self):
        return self.atom.state if self.atom else "TOMB"

    def is_alive(self):
        if self.is_boss:
            return self.health > 0
        return self.atom and self.atom.state != "TOMB" and 0 < self.atom.T < 100

    def update_from_state(self):
        if self.state == "HOT":
            self.speed_x = ENEMY_BASE_SPEED * (2.4 if not self.is_boss else 1.8)
            self.shoot_cooldown = ENEMY_SHOOT_DELAY * (0.35 if not self.is_boss else 0.55)
        elif self.state == "WARM":
            self.speed_x = ENEMY_BASE_SPEED * 1.45
            self.shoot_cooldown = ENEMY_SHOOT_DELAY * 0.65
        else:
            self.speed_x = ENEMY_BASE_SPEED
            self.shoot_cooldown = ENEMY_SHOOT_DELAY


class PowerUp:
    def __init__(self, x, y, ptype: str):
        self.x, self.y = x, y
        self.type = ptype
        self.speed = 95.0
        self.lifetime = 9.0
        self.spawn_time = time.monotonic()


class ThermalInvaders:
    def __init__(self, display, runtime=None):
        self.display = display
        self.runtime = runtime
        self.renderer = display.renderer if display else None

        self.level = 1
        self.score = 0
        self.lives = LIVES
        self.combo = 0
        self.last_combo_kill = 0.0
        self.combo_timeout = 2.3

        self.player_x = self.player_y = 0.0
        self.game_over = self.won = self.active = self._initialized = False
        self.panel_w = self.panel_h = 0

        self.enemies: List[Enemy] = []
        self.bullets = []           # (x, y)
        self.enemy_bullets = []
        self.explosions = []
        self.powerups: List[PowerUp] = []

        self.last_player_shot = 0.0
        self.enemy_direction = 1
        self._last_draw = 0.0
        self._reset_counter = 0

        self.rapid_fire_until = 0.0
        self.multi_shot_until = 0.0

        if HAS_KARMAZYN and runtime:
            runtime.events.on("state_changed", self._on_enemy_state_changed)

    def _on_enemy_state_changed(self, atom):
        for e in self.enemies:
            if e.atom is atom:
                e.update_from_state()
                break

    def start(self):
        if not self.display or not self.display.available:
            return "Tryb graficzny niedostępny."
        self.active = True
        self._initialized = False
        self.renderer.claim_left(self.draw, "THERMAL")

    def stop(self):
        global _THERMAL_GAME
        if self.active and self.renderer:
            self.renderer.release_left()
        self.active = False
        # Usuń wszystkie atomy gry przy zamykaniu (czyszczenie)
        self._cleanup_atoms()
        _THERMAL_GAME = None

    def _cleanup_atoms(self):
        """Usuwa wszystkie atomy związane z grą (wrogowie, power‑upy) z phi‑space."""
        if not HAS_KARMAZYN or not self.runtime:
            return
        to_delete = []
        for aid, atom in self.runtime.matrix._atoms.items():
            if aid.startswith("invader_") or aid.startswith("powerup_"):
                to_delete.append(aid)
        for aid in to_delete:
            try:
                self.runtime.delete_atom(aid)
            except:
                pass

    def _reset_game(self):
        # Najpierw posprzątaj stare atomy
        self._cleanup_atoms()

        self._reset_counter += 1
        self.level = 1
        self.score = 0
        self.lives = LIVES
        self.combo = 0
        self.game_over = False
        self.won = False
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.explosions.clear()
        self.powerups.clear()
        self.enemy_direction = 1
        self.rapid_fire_until = 0.0
        self.multi_shot_until = 0.0
        self._create_enemies()

    def _create_enemies(self):
        self.enemies.clear()
        is_boss_level = (self.level % 4 == 0)

        if is_boss_level:
            # Boss – upewnij się, że panel_w jest znany
            if self.panel_w == 0:
                self.panel_w = 800  # fallback
            boss = Enemy(self.panel_w//2 - 45, 70, 0, self.runtime, self._reset_counter, is_boss=True)
            boss.speed_x = 48.0
            self.enemies.append(boss)
        else:
            cols = min(7, 4 + self.level // 2)
            rows = min(4, 2 + (self.level - 1) // 3)
            margin_x, margin_y = 35, 48
            spacing_x = ENEMY_WIDTH + 14
            spacing_y = ENEMY_HEIGHT + 12
            idx = 0
            for row in range(rows):
                for col in range(cols):
                    x = margin_x + col * spacing_x
                    y = margin_y + row * spacing_y
                    self.enemies.append(Enemy(x, y, idx, self.runtime, self._reset_counter))
                    idx += 1

    def _destroy_enemy(self, enemy: Enemy, give_points=True):
        if enemy not in self.enemies:
            return
        self.enemies.remove(enemy)

        now = time.monotonic()

        # Combo – tylko HOT wrogowie zwiększają, brak resetu przy cold/warm
        if not enemy.is_boss and enemy.state == "HOT":
            if now - self.last_combo_kill < self.combo_timeout:
                self.combo += 1
            else:
                self.combo = 1
            self.last_combo_kill = now

        if give_points:
            if enemy.is_boss:
                self.score += BOSS_SCORE
            else:
                multiplier = 1 + (self.combo - 1) * 0.6
                self.score += int(SCORE_PER_KILL * multiplier)

        self.explosions.append((enemy.x + (45 if enemy.is_boss else ENEMY_WIDTH//2),
                                enemy.y + (25 if enemy.is_boss else ENEMY_HEIGHT//2),
                                now + 0.4))

        # Power-up drop (tylko z gorących zwykłych wrogów)
        if not enemy.is_boss and enemy.state == "HOT" and np.random.rand() < 0.29:
            ptype = np.random.choice(["life", "rapid", "multi", "freeze"])
            self.powerups.append(PowerUp(enemy.x + ENEMY_WIDTH//2, enemy.y + ENEMY_HEIGHT//2, ptype))

        if not self.enemies and not self.game_over:
            if self.level >= MAX_LEVEL:
                # Wygrana
                self.won = True
                self.game_over = True
            else:
                self.level += 1
                self._create_enemies()

    def _resize(self, ctx):
        w, h = ctx.rect.w, ctx.rect.h
        if w == self.panel_w and h == self.panel_h and self._initialized:
            return
        self.panel_w, self.panel_h = w, h
        if not self._initialized and self.active:
            self.player_x = self.panel_w // 2 - PLAYER_WIDTH // 2
            self.player_y = self.panel_h - PLAYER_HEIGHT - 28
            self._reset_game()
            self._initialized = True
        else:
            # Aktualizacja pozycji gracza przy zmianie rozmiaru
            self.player_x = max(0, min(self.panel_w - PLAYER_WIDTH, self.player_x))
            self.player_y = self.panel_h - PLAYER_HEIGHT - 28

    def _handle_input(self, dt):
        if not PYGAME_OK or not self.active or self.game_over:
            return
        keys = pygame.key.get_pressed()

        if keys[pygame.K_LEFT]:  self.player_x -= PLAYER_SPEED * dt
        if keys[pygame.K_RIGHT]: self.player_x += PLAYER_SPEED * dt
        self.player_x = max(0, min(self.panel_w - PLAYER_WIDTH, self.player_x))

        now = time.monotonic()
        shoot_delay = 0.10 if now < self.rapid_fire_until else PLAYER_SHOOT_DELAY

        if keys[pygame.K_SPACE] and now - self.last_player_shot >= shoot_delay:
            if len(self.bullets) < MAX_BULLETS:
                self.last_player_shot = now
                bx = self.player_x + PLAYER_WIDTH//2 - BULLET_SIZE//2
                by = self.player_y

                if now < self.multi_shot_until:
                    # multi-shot – każdy pocisk osobno, ale limit 3
                    for off in (-16, 0, 16):
                        if len(self.bullets) + 1 <= MAX_BULLETS:
                            self.bullets.append((bx + off, by))
                else:
                    self.bullets.append((bx, by))

        if keys[pygame.K_F1]:
            self.stop()

    def _update_bullets(self, dt):
        # Player bullets
        new_bullets = []
        for bx, by in self.bullets:
            by += BULLET_SPEED * dt
            if by < -20: continue

            hit = False
            for e in self.enemies[:]:
                ew = 90 if e.is_boss else ENEMY_WIDTH
                eh = 50 if e.is_boss else ENEMY_HEIGHT
                if (bx + BULLET_SIZE > e.x and bx < e.x + ew and
                    by + BULLET_SIZE > e.y and by < e.y + eh):
                    e.cool(COOLING_PER_HIT)
                    if not e.is_alive():
                        self._destroy_enemy(e)
                    hit = True
                    break
            if not hit:
                new_bullets.append((bx, by))
        self.bullets = new_bullets

        # Enemy bullets
        new_enemy_bullets = []
        for bx, by in self.enemy_bullets:
            by += -BULLET_SPEED * dt
            if by > self.panel_h + 10: continue

            if (bx + BULLET_SIZE > self.player_x and bx < self.player_x + PLAYER_WIDTH and
                by + BULLET_SIZE > self.player_y and by < self.player_y + PLAYER_HEIGHT):
                self.lives -= 1
                self.explosions.append((self.player_x + PLAYER_WIDTH//2,
                                        self.player_y + PLAYER_HEIGHT//2,
                                        time.monotonic() + 0.6))
                if self.lives <= 0:
                    self.game_over = True
                continue
            new_enemy_bullets.append((bx, by))
        self.enemy_bullets = new_enemy_bullets

    def _update_enemies(self, dt):
        if not self.enemies:
            return
        now = time.monotonic()

        min_x = min(e.x for e in self.enemies)
        max_x = max(e.x + (90 if e.is_boss else ENEMY_WIDTH) for e in self.enemies)

        if self.enemy_direction == 1 and max_x >= self.panel_w - 20:
            self.enemy_direction = -1
            for e in self.enemies: e.y += ENEMY_DROP_STEP
        elif self.enemy_direction == -1 and min_x <= 10:
            self.enemy_direction = 1
            for e in self.enemies: e.y += ENEMY_DROP_STEP

        for e in self.enemies:
            if e.frozen_until > now:
                continue

            e.x += self.enemy_direction * e.speed_x * dt
            e.heat(ENEMY_HEAT_RATE * dt * (1.15 if self.level > 3 else 1.0))

            if not e.is_alive():
                self._destroy_enemy(e, give_points=not e.is_boss)

            # Shooting (każdy wróg niezależnie)
            if now - e.last_shot >= e.shoot_cooldown:
                bx = e.x + (45 if e.is_boss else ENEMY_WIDTH//2) - BULLET_SIZE//2
                by = e.y + (48 if e.is_boss else ENEMY_HEIGHT)
                self.enemy_bullets.append((bx, by))
                e.last_shot = now

        # Sprawdź, czy wrogowie dotarli do dołu
        for e in self.enemies:
            if e.y + 60 >= self.player_y:
                self.game_over = True
                break

    def _update_powerups(self, dt):
        now = time.monotonic()
        new_pups = []
        for p in self.powerups:
            p.y += p.speed * dt
            if p.y > self.panel_h or now - p.spawn_time > p.lifetime:
                continue

            if (abs(p.x - (self.player_x + PLAYER_WIDTH//2)) < 28 and
                abs(p.y - (self.player_y + PLAYER_HEIGHT//2)) < 28):
                self._apply_powerup(p.type)
                continue
            new_pups.append(p)
        self.powerups = new_pups

    def _apply_powerup(self, ptype: str):
        now = time.monotonic()
        if ptype == "life":
            self.lives = min(5, self.lives + 1)
        elif ptype == "rapid":
            self.rapid_fire_until = now + 8.5
        elif ptype == "multi":
            self.multi_shot_until = now + 7.5
        elif ptype == "freeze":
            for e in self.enemies:
                e.freeze(3.0)

    def update(self, dt):
        if not self.active or self.game_over:
            return
        self._handle_input(dt)
        self._update_bullets(dt)
        self._update_enemies(dt)
        self._update_powerups(dt)

        now = time.monotonic()
        self.explosions = [exp for exp in self.explosions if exp[2] > now]

    def draw(self, ctx):
        if not self.active: return
        self._resize(ctx)
        now = time.monotonic()
        dt = min(0.033, now - getattr(self, '_last_draw', now))
        self._last_draw = now
        self.update(dt)

        ctx.clear(C_BG)

        # Enemies
        for e in self.enemies:
            color = C_BOSS if e.is_boss else C_ENEMY_HOT if e.state == "HOT" else \
                    C_ENEMY_WARM if e.state == "WARM" else C_ENEMY_COLD
            if e.frozen_until > now:
                color = C_FROZEN

            w = 90 if e.is_boss else ENEMY_WIDTH
            h = 50 if e.is_boss else ENEMY_HEIGHT
            pygame.draw.rect(ctx.surface, color, (e.x, e.y, w, h))

        # Player
        pygame.draw.rect(ctx.surface, C_PLAYER,
                         (self.player_x, self.player_y, PLAYER_WIDTH, PLAYER_HEIGHT))
        pygame.draw.rect(ctx.surface, (160, 240, 160),
                         (self.player_x + PLAYER_WIDTH//2 - 4, self.player_y - 9, 8, 13))

        # Bullets
        for bx, by in self.bullets:
            pygame.draw.rect(ctx.surface, C_BULLET, (bx, by, BULLET_SIZE, BULLET_SIZE))
        for bx, by in self.enemy_bullets:
            pygame.draw.rect(ctx.surface, (255, 80, 80), (bx, by, BULLET_SIZE, BULLET_SIZE))

        # Explosions
        for x, y, end in self.explosions:
            pygame.draw.circle(ctx.surface, C_EXPLOSION, (int(x), int(y)), 15)

        # Power-ups
        font = ctx.font
        for p in self.powerups:
            pygame.draw.circle(ctx.surface, C_POWERUP, (int(p.x), int(p.y)), 14)
            sym = {"life": "❤️", "rapid": "⚡", "multi": "3×", "freeze": "❄️"}[p.type]
            surf = font.render(sym, True, (0, 0, 0))
            ctx.surface.blit(surf, (p.x - surf.get_width()//2, p.y - surf.get_height()//2 - 1))

        # UI
        ctx.surface.blit(font.render(f"SCORE: {self.score}  ×{max(1, self.combo)}", True, C_UI), (12, 12))
        ctx.surface.blit(font.render(f"LEVEL: {self.level}/{MAX_LEVEL}", True, C_UI), (12, 42))
        ctx.surface.blit(font.render(f"LIVES: {self.lives}", True, C_UI), (12, 72))
        if self.rapid_fire_until > now:
            ctx.surface.blit(font.render("RAPID", True, (255, 200, 100)), (12, 102))
        if self.multi_shot_until > now:
            ctx.surface.blit(font.render("MULTI", True, (255, 200, 100)), (12, 122))

        if self.game_over:
            if self.won:
                msg = f"YOU WIN! Level {self.level} completed!"
                col = (80, 255, 120)
            else:
                msg = "GAME OVER"
                col = (255, 70, 70)
            surf = font.render(msg, True, col)
            ctx.surface.blit(surf, (self.panel_w//2 - surf.get_width()//2, self.panel_h//2 - 50))

            restart = font.render("Press R to restart", True, (255, 220, 100))
            ctx.surface.blit(restart, (self.panel_w//2 - restart.get_width()//2, self.panel_h//2 + 10))

            if PYGAME_OK and pygame.key.get_pressed()[pygame.K_r]:
                self._reset_game()
                self.game_over = False
                self.won = False

        pygame.draw.rect(ctx.surface, (180, 60, 60), ctx.rect, 3)


_THERMAL_GAME = None

def cmd_thermal(args, display, runtime=None):
    global _THERMAL_GAME
    if _THERMAL_GAME and _THERMAL_GAME.active:
        return "Gra już działa. Użyj F1 aby wyjść."
    _THERMAL_GAME = ThermalInvaders(display, runtime)
    _THERMAL_GAME.start()
    return "Thermal Invaders v2.9 uruchomione! 🔥"


if __name__ == "__main__":
    print("Thermal Invaders v2.9 – uruchom przez: THERMAL")