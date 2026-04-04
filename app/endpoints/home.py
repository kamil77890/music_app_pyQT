from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter(tags=["Home"])


@router.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@router.get("/")
def home(request: Request):
    """Automatically generates endpoint documentation from registered routes."""
    app = request.app
    endpoints = {}
    
    for route in app.routes:
        if hasattr(route, 'path') and route.path in ['/', '/favicon.ico']:
            continue
        
        if hasattr(route, 'methods'):
            methods = ', '.join(sorted(route.methods - {'HEAD', 'OPTIONS'}))
        else:
            continue
        
        path = getattr(route, 'path', None)
        if not path:
            continue
        
        description = ""
        if hasattr(route, 'summary') and route.summary:
            description = f" - {route.summary}"
        
        # Build the endpoint entry
        endpoints[path] = f"{methods} {path}{description}"
    
    return dict(sorted(endpoints.items()))
