from fastapi import APIRouter

router = APIRouter()

@router.get('/mentions')
def get_mentions():
    return {'mentions': []}
