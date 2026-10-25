"""The engine: the machinery under the film.

``fight/`` draws the bodies, ``engine/`` owns the things a body *has*: inertia
(``biomechanics``), objects it can lose (``weapons_and_props``), forces it can
throw (``superpowers``), the ground it breaks (``destruction_physics``), the lens
that watches it (``camera_director``) and the score that carries it
(``soundtrack_engine``).

The split is deliberate. A module in here may be imported by the renderer, but
nothing in here imports the choreography: given a timeline of events it returns
geometry, and the film decides when to ask.
"""
