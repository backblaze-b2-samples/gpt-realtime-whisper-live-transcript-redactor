"""Glossary CRUD endpoints — backed by config/glossary.json in B2."""

import logging

from fastapi import APIRouter

from app.service.glossary import load_glossary, save_glossary
from app.types import Glossary

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/glossary", response_model=Glossary)
async def get_glossary_endpoint():
    return load_glossary()


@router.put("/glossary", response_model=Glossary)
async def put_glossary_endpoint(glossary: Glossary):
    save_glossary(glossary)
    return load_glossary()
