"""
ai package – Adaptive combat AI for enemy characters.

Modules:
    ai_core               – Central brain (AIBrain) that orchestrates all sub-systems
    combat_intent_system  – Frame-by-frame intent evaluation
    aggression_system     – Human-like pressure, tempo, match-flow, punish
    build_difficulty_adapter – Behavior shaping based on player build type
    desperation_mode      – Low-HP comeback intelligence & rage mode
    phase_system          – Combat phase state machine (Observe → Counter → Desperation → Rage)
    adaptive_learning     – Real-time per-match player pattern learning
    attack_style_system   – Blendable combat archetypes (7 styles)
    difficulty_balancer   – Dynamic rubber-banding difficulty adjustment
    ai_system             – Legacy personality definitions & DuelistBehavior
    behavior_analyzer     – Player style detection
    data_logger           – Match data logging
    persistence           – Archetype win-rate persistence
    stats                 – Match statistics tracking
"""
