"""This PC, as Settings > About and Setup show it: its graphics card, processor and memory,
whether the AI models run on the card, where each kind of picture starts (Fast or Best) and how
long a typical one takes; and testing it again."""

import sqlite3
from typing import Literal

from fastapi import APIRouter

from mado import hardware
from mado.ai import Ai
from mado.api.common import ApiModel, Database, Models, ThisPc
from mado.core.hardware import abilities, best_card
from mado.pc_check import PcCheck

router = APIRouter()


class CardOut(ApiModel):
    name: str
    maker: Literal["nvidia", "amd", "intel", "other"]
    memory: int | None  # bytes of its own
    integrated: bool  # the processor's graphics
    driver: str | None


class AbilityOut(ApiModel):
    kind: Literal["photo", "drawing"]
    quality: Literal["fast", "best"]
    model: str
    pace: Literal["ready", "slow"]
    seconds: float  # a phone's 12-megapixel photo made for a 4K screen
    download: bool  # fetched the first time it's asked for


class StartsOn(ApiModel):
    photo: Literal["fast", "best"]
    drawing: Literal["fast", "best"]


class MeasuredOut(ApiModel):
    at: str
    tested: bool  # by a test, rather than by pictures made since
    pictures: int  # pictures made since


class Pc(ApiModel):
    card: CardOut | None
    processor: str | None
    cores: int | None
    memory: int | None
    checked_at: str | None  # None before it's tested
    on_card: bool | None  # the AI models run on the card; None before it's tested
    problem: str | None  # what the card said when they didn't
    place: Literal["card", "processor"]
    testing: bool
    timing: bool
    measured: MeasuredOut | None  # None while the times are a guess
    starts_on: StartsOn
    abilities: list[AbilityOut]


@router.get("/pc")
def this_pc(pc: ThisPc, conn: Database, ai: Models) -> Pc:
    return _pc(pc, conn, ai)


@router.post("/pc/test")
def test_this_pc(pc: ThisPc, conn: Database, ai: Models) -> Pc:
    """Tests this PC again, timing each model, in the background."""
    pc.test()
    return _pc(pc, conn, ai)


def _pc(pc: PcCheck, conn: sqlite3.Connection, ai: Ai) -> Pc:
    facts = pc.facts()
    _, checked = hardware.stored(conn)
    here = hardware.here(conn)
    measured = hardware.measured(conn)
    card = best_card(facts.cards)
    starts = ai.starts_on(here)
    checking = pc.checking()
    return Pc(
        card=CardOut(
            name=card.name,
            maker=card.maker,
            memory=card.memory,
            integrated=card.integrated,
            driver=card.driver,
        )
        if card
        else None,
        processor=facts.processor,
        cores=facts.cores,
        memory=facts.memory,
        checked_at=checked.at if checked else None,
        on_card=checked.ai if checked else None,
        problem=checked.problem if checked else None,
        place=here.place,
        testing=checking is not None,
        timing=checking.timing if checking else False,
        measured=MeasuredOut(at=measured.at, tested=measured.tested, pictures=measured.pictures)
        if measured
        else None,
        starts_on=StartsOn(photo=starts["photo"], drawing=starts["drawing"]),
        abilities=[
            AbilityOut(
                kind=each.kind,
                quality=each.quality,
                model=each.model,
                pace=each.pace,
                seconds=each.seconds,
                download=each.download,
            )
            for each in abilities(here.place, card, here.speeds)
        ],
    )
