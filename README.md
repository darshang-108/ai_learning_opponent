## Overview

AI Learning Opponent is a real-time adaptive combat AI framework 
built inside a 2D fighting simulation. 

The project explores behavioral modeling, dynamic difficulty adjustment, 
state-based decision systems, and reinforcement-inspired personality selection 
within a deterministic offline environment.

## Why This Project?

Traditional enemy AI relies on static behavior trees or scripted patterns.
This project experiments with:

- Real-time player behavior profiling
- Strategy adaptation across matches
- Phase-based escalation logic
- Competitive rubber-banding without feeling unfair
- Modular AI architecture suitable for reuse

The game serves as a controlled simulation environment for testing adaptive AI design.

## Architecture Overview

Player Input → Behavior Analyzer → Personality Selector  
→ AIBrain Orchestrator → Subsystems (Intent, Aggression, Phase, etc.)  
→ Enemy Action Execution → Combat System

## Technical Highlights

- Modular AI architecture with subsystem isolation
- Epsilon-greedy strategy selection
- Persistent cross-session learning (JSON store)
- Match analytics via matplotlib
- State-driven game loop (MENU / PLAYING / GAME_OVER)
- Procedural SFX generation (no external audio files)
- Offline executable packaging via PyInstaller

## Future Improvements

- Reinforcement learning policy experiments
- Networked multiplayer mode
- AI telemetry dashboard
- Performance profiling & optimization
- Plugin-based AI module system