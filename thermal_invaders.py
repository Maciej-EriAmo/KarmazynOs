#!/usr/bin/env python3
"""
thermal_invaders.py — Thermal Invaders v2.6
============================================
- Wyjście z gry: F1 (ESC zamyka cały system)
- Kolizje i termodynamika działają poprawnie
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

# Stałe gry
PHI_DIM = 15
PLAYER_WIDTH, PLAYER_HEIGHT = 30, 20
PLAYER_SPEED = 400.0
BULLET_SIZE, BULLET_SPEED = 6, -600.0   # ujemna = w górę
ENEMY_WIDTH, ENEMY_HEIGHT = 28, 24
ENEMY_BASE_SPEED = 60.0
ENEMY_DROP_STEP = 16
ENEMY_SHOOT_DELAY = 1.2
PLAYER_SHOOT_DELAY = 0.25
LIVES = 3
SCORE_PER_KILL = 10
ENEMY_HEAT_RATE = 8.0
COOLING_PER_HIT = 25.0

C_PLAYER = (100,220,100)
C_BULLET = (255,255,100)
C_ENEMY_COLD = (40,80,140)
C_ENEMY_WARM = (60,160,255)
C_ENEMY_HOT = (255,80,40)
C_EXPLOSION = (255,160,20)
C_BG = (12,12,20)
C_UI = (220,220,220)


class Enemy:
    def __init__(self, x, y, idx, runtime, reset_id=0):
        self.x, self.y = x, y
        self.idx = idx
        self.atom = None
        self.speed_x = ENEMY_BASE_SPEED
        self.shoot_cooldown = ENEMY_SHOOT_DELAY

        vec = np.random.randn(PHI_DIM).astype(np.float32)
        vec[0] = x / 100.0
        vec[1] = y / 100.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        unique_id = f"invader_{reset_id}_{idx}"
        if HAS_KARMAZYN and runtime:
            if runtime.has_atom(unique_id):
                try:
                    runtime.delete_atom(unique_id)
                except:
                    pass
            self.atom = runtime.create_atom(unique_id, vec, f"{x},{y}", 40.0)
        else:
            self.atom = Atom(unique_id, vec, f"{x},{y}", 40.0)

    def heat(self, amount):
        if self.atom:
            if hasattr(self.atom, 'heat'):
                self.atom.heat(amount)
            else:
                self.atom.T = min(100.0, self.atom.T + amount)

    def cool(self, amount):
        if self.atom:
            if hasattr(self.atom, 'cool'):
                self.atom.cool(amount)
            else:
                self.atom.T = max(0.0, self.atom.T - amount)

    @property
    def T(self):
        return self.atom.T if self.atom else 0.0

    @property
    def state(self):
        return self.atom.state if self.atom else "TOMB"

    def is_alive(self):
        if not self.atom:
            return False
        return self.atom.state != "TOMB" and 0 < self.atom.T < 100

    def update_from_state(self):
        if not self.atom:
            return
        if self.atom.state == "HOT":
            self.speed_x = ENEMY_BASE_SPEED * 2.2
            self.shoot_cooldown = ENEMY_SHOOT_DELAY * 0.4
        elif self.atom.state == "WARM":
            self.speed_x = ENEMY_BASE_SPEED * 1.4
            self.shoot_cooldown = ENEMY_SHOOT_DELAY * 0.7
        else:
            self.speed_x = ENEMY_BASE_SPEED
            self.shoot_cooldown = ENEMY_SHOOT_DELAY


class ThermalInvaders:
    def __init__(self, display, runtime=None):
        self.display = display
        self.runtime = runtime
        self.renderer = display.renderer if display else None

        self.player_x = self.player_y = 0.0
        self.lives = LIVES
        self.score = 0
        self.game_over = self.won = self.active = self._initialized = False
        self.panel_w = self.panel_h = 0

        self.enemies = []
        self.bullets = []          # (x, y)
        self.enemy_bullets = []    # (x, y)
        self.explosions = []       # (x, y, end_time)

        self.last_player_shot = self.last_enemy_shot = 0.0
        self.enemy_direction = 1
        self._last_draw = 0.0
        self._reset_counter = 0

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
        _THERMAL_GAME = None

    def _reset_game(self):
        self._reset_counter += 1
        self.player_x = max(0, self.panel_w//2 - PLAYER_WIDTH//2)
        self.player_y = self.panel_h - PLAYER_HEIGHT - 20
        self.lives, self.score = LIVES, 0
        self.game_over = self.won = False
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.explosions.clear()
        self.enemy_direction = 1
        self.last_player_shot = self.last_enemy_shot = time.monotonic()
        self._create_enemies()

    def _create_enemies(self):
        self.enemies.clear()
        margin_x, margin_y = 40, 60
        cols, rows = 5, 3
        spacing_x = ENEMY_WIDTH + 12
        spacing_y = ENEMY_HEIGHT + 10
        idx = 0
        for row in range(rows):
            for col in range(cols):
                x = margin_x + col * spacing_x
                y = margin_y + row * spacing_y
                self.enemies.append(Enemy(x, y, idx, self.runtime, self._reset_counter))
                idx += 1

    def _destroy_enemy(self, enemy, give_points=True):
        if enemy not in self.enemies:
            return
        self.enemies.remove(enemy)
        if give_points:
            self.score += SCORE_PER_KILL
        self.explosions.append((enemy.x + ENEMY_WIDTH//2, enemy.y + ENEMY_HEIGHT//2,
                                time.monotonic() + 0.3))
        print(f"[DEBUG] Enemy destroyed at ({enemy.x},{enemy.y}), score={self.score}")
        if not self.enemies and not self.game_over:
            self.won = True
            self.game_over = True

    def _resize(self, ctx):
        w, h = ctx.rect.w, ctx.rect.h
        if w == self.panel_w and h == self.panel_h and self._initialized:
            return
        self.panel_w, self.panel_h = w, h
        if not self._initialized and self.active:
            self._reset_game()
            self._initialized = True
        else:
            self.player_x = max(0, min(self.panel_w - PLAYER_WIDTH, self.player_x))
            self.player_y = self.panel_h - PLAYER_HEIGHT - 20

    def _handle_input(self, dt):
        if not PYGAME_OK or not self.active or self.game_over:
            return
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            self.player_x -= PLAYER_SPEED * dt
        if keys[pygame.K_RIGHT]:
            self.player_x += PLAYER_SPEED * dt
        self.player_x = max(0, min(self.panel_w - PLAYER_WIDTH, self.player_x))

        now = time.monotonic()
        if keys[pygame.K_SPACE] and now - self.last_player_shot >= PLAYER_SHOOT_DELAY:
            self.last_player_shot = now
            bx = self.player_x + PLAYER_WIDTH//2 - BULLET_SIZE//2
            by = self.player_y
            self.bullets.append((bx, by))

        # Wyjście z gry: F1 (ESC zamyka cały system)
        if keys[pygame.K_F1]:
            self.stop()

    def _update_bullets(self, dt):
        # Pociski gracza (w górę)
        new_bullets = []
        for bx, by in self.bullets:
            by += BULLET_SPEED * dt
            if by + BULLET_SIZE > 0:
                new_bullets.append((bx, by))
                for enemy in self.enemies[:]:
                    if (bx + BULLET_SIZE > enemy.x and bx < enemy.x + ENEMY_WIDTH and
                        by + BULLET_SIZE > enemy.y and by < enemy.y + ENEMY_HEIGHT):
                        enemy.cool(COOLING_PER_HIT)
                        print(f"[DEBUG] Hit enemy at ({enemy.x},{enemy.y}), T={enemy.T:.1f}")
                        if not enemy.is_alive():
                            self._destroy_enemy(enemy, give_points=True)
                        break
        self.bullets = new_bullets

        # Pociski wrogów (w dół)
        new_enemy_bullets = []
        for bx, by in self.enemy_bullets:
            by += -BULLET_SPEED * dt
            if by < self.panel_h:
                new_enemy_bullets.append((bx, by))
                if (bx + BULLET_SIZE > self.player_x and bx < self.player_x + PLAYER_WIDTH and
                    by + BULLET_SIZE > self.player_y and by < self.player_y + PLAYER_HEIGHT):
                    self.lives -= 1
                    self.explosions.append((self.player_x + PLAYER_WIDTH//2,
                                            self.player_y + PLAYER_HEIGHT//2,
                                            time.monotonic() + 0.5))
                    print(f"[DEBUG] Player hit, lives={self.lives}")
                    if self.lives <= 0:
                        self.game_over = True
                    else:
                        self.bullets.clear()
                        self.enemy_bullets.clear()
                        self.player_x = max(0, self.panel_w//2 - PLAYER_WIDTH//2)
                    break
        self.enemy_bullets = new_enemy_bullets

    def _update_enemies(self, dt):
        if not self.enemies:
            return
        min_x = min(e.x for e in self.enemies)
        max_x = max(e.x for e in self.enemies)
        if self.enemy_direction == 1 and max_x + ENEMY_WIDTH >= self.panel_w - 10:
            self.enemy_direction = -1
            for e in self.enemies:
                e.y += ENEMY_DROP_STEP
        elif self.enemy_direction == -1 and min_x <= 10:
            self.enemy_direction = 1
            for e in self.enemies:
                e.y += ENEMY_DROP_STEP

        for e in self.enemies:
            e.x += self.enemy_direction * e.speed_x * dt

        now = time.monotonic()
        if self.enemies and now - self.last_enemy_shot >= ENEMY_SHOOT_DELAY:
            self.last_enemy_shot = now
            shooter = max(self.enemies, key=lambda e: e.T)
            bx = shooter.x + ENEMY_WIDTH//2 - BULLET_SIZE//2
            by = shooter.y + ENEMY_HEIGHT
            self.enemy_bullets.append((bx, by))

        for e in self.enemies:
            e.heat(ENEMY_HEAT_RATE * dt)
            if not e.is_alive():
                self._destroy_enemy(e, give_points=False)

        for e in self.enemies:
            if e.y + ENEMY_HEIGHT >= self.player_y:
                self.game_over = True
                break

    def _update_explosions(self):
        now = time.monotonic()
        self.explosions = [(x, y, end) for (x, y, end) in self.explosions if end > now]

    def update(self, dt):
        if not self.active or self.game_over:
            return
        self._handle_input(dt)
        self._update_bullets(dt)
        self._update_enemies(dt)
        self._update_explosions()

    def draw(self, ctx):
        if not self.active:
            return
        self._resize(ctx)
        now = time.monotonic()
        if not hasattr(self, '_last_draw'):
            self._last_draw = now
            dt = 1/60
        else:
            dt = min(0.033, now - self._last_draw)
            self._last_draw = now
        self.update(dt)

        ctx.clear(C_BG)
        for e in self.enemies:
            if e.state == "HOT":
                color = C_ENEMY_HOT
            elif e.state == "WARM":
                color = C_ENEMY_WARM
            else:
                color = C_ENEMY_COLD
            rect = pygame.Rect(e.x, e.y, ENEMY_WIDTH, ENEMY_HEIGHT)
            pygame.draw.rect(ctx.surface, color, rect)
            eye_w = ENEMY_WIDTH // 5
            eye_h = ENEMY_HEIGHT // 5
            pygame.draw.rect(ctx.surface, (255,255,255),
                             (e.x + ENEMY_WIDTH//3, e.y + ENEMY_HEIGHT//3, eye_w, eye_h))
            pygame.draw.rect(ctx.surface, (255,255,255),
                             (e.x + 2*ENEMY_WIDTH//3 - eye_w, e.y + ENEMY_HEIGHT//3, eye_w, eye_h))

        player_rect = pygame.Rect(self.player_x, self.player_y, PLAYER_WIDTH, PLAYER_HEIGHT)
        pygame.draw.rect(ctx.surface, C_PLAYER, player_rect)
        gun_w = 8
        gun_x = self.player_x + PLAYER_WIDTH//2 - gun_w//2
        gun_y = self.player_y - 6
        pygame.draw.rect(ctx.surface, (150,200,150), (gun_x, gun_y, gun_w, 8))

        for bx, by in self.bullets:
            pygame.draw.rect(ctx.surface, C_BULLET, (bx, by, BULLET_SIZE, BULLET_SIZE))
        for bx, by in self.enemy_bullets:
            pygame.draw.rect(ctx.surface, (255,100,100), (bx, by, BULLET_SIZE, BULLET_SIZE))

        for x, y, _ in self.explosions:
            pygame.draw.circle(ctx.surface, C_EXPLOSION, (int(x), int(y)), 12)

        font = ctx.font
        score_surf = font.render(f"SCORE: {self.score}", True, C_UI)
        lives_surf = font.render(f"LIVES: {self.lives}", True, C_UI)
        ctx.surface.blit(score_surf, (ctx.rect.x + 10, ctx.rect.y + 10))
        ctx.surface.blit(lives_surf, (ctx.rect.x + 10, ctx.rect.y + 40))

        if self.game_over:
            msg = "YOU WIN!  R = restart" if self.won else "GAME OVER!  R = restart"
            msg_surf = font.render(msg, True, (255,200,100))
            tw = msg_surf.get_width()
            th = msg_surf.get_height()
            ctx.surface.blit(msg_surf, (ctx.rect.centerx - tw//2, ctx.rect.centery - th//2))
            if PYGAME_OK and pygame.key.get_pressed()[pygame.K_r]:
                self._reset_game()
                self.game_over = self.won = False

        pygame.draw.rect(ctx.surface, (180,60,60), ctx.rect, 2)


_THERMAL_GAME = None

def cmd_thermal(args, display, runtime=None):
    global _THERMAL_GAME
    if not display or not display.available:
        return "Tryb graficzny niedostępny – wpisz DISPLAY."
    if _THERMAL_GAME and _THERMAL_GAME.active:
        return "Gra już działa. Użyj F1, aby wyjść z gry."
    _THERMAL_GAME = ThermalInvaders(display, runtime)
    _THERMAL_GAME.start()
    return "Thermal Invaders v2.6 – strzałki, spacja, F1 – wyjście."

if __name__ == "__main__":
    print("Thermal Invaders – uruchom przez shell: THERMAL")