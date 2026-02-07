from pydantic import BaseModel


class Point2D(BaseModel):
    x: float
    y: float


class Point3D(BaseModel):
    x: float
    y: float
    z: float


class BoundingBox3D(BaseModel):
    min: Point3D
    max: Point3D


class Plane3D(BaseModel):
    point: Point3D
    normal: Point3D


class DeviceInfo(BaseModel):
    user_agent: str
    platform: str
    screen_width: int
    screen_height: int
