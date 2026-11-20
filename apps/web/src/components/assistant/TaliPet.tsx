import { Canvas, useFrame } from '@react-three/fiber'
import { useRef, type RefObject } from 'react'
import * as THREE from 'three'

type Pointer = { x: number; y: number }
export type TaliPose = 'idle' | 'walk' | 'tired' | 'sleep' | 'slip'

const fur = '#9a5b3f'
const furLight = '#ba7b54'
const furDark = '#6b3e32'
const cream = '#f3d7b2'
const navy = '#1e2a46'
const navyLight = '#334363'
const teal = '#04b9ae'

function Ball({ position, scale, color, roughness = 0.85 }: {
  position: [number, number, number]; scale: [number, number, number]; color: string; roughness?: number
}) {
  return <mesh position={position} scale={scale} castShadow receiveShadow>
    <sphereGeometry args={[1, 40, 32]} />
    <meshPhysicalMaterial color={color} roughness={roughness} clearcoat={roughness < 0.4 ? 0.65 : 0.05} />
  </mesh>
}

function Stroke({ points, color, width = 0.007 }: { points: [number, number, number][]; color: string; width?: number }) {
  const curve = new THREE.CatmullRomCurve3(points.map(point => new THREE.Vector3(...point)))
  return <mesh>
    <tubeGeometry args={[curve, 18, width, 6, false]} />
    <meshStandardMaterial color={color} roughness={0.75} />
  </mesh>
}

function polygon(points: [number, number][]) {
  const shape = new THREE.Shape()
  shape.moveTo(...points[0])
  points.slice(1).forEach(point => shape.lineTo(...point))
  shape.closePath()
  return shape
}

const shirt = polygon([[-0.19, 0.17], [0.19, 0.17], [0.13, -0.63], [-0.13, -0.63]])
const leftLapel = polygon([[-0.13, 0.17], [-0.51, -0.04], [-0.3, -0.51], [-0.045, -0.28]])
const rightLapel = polygon([[0.13, 0.17], [0.51, -0.04], [0.3, -0.51], [0.045, -0.28]])
const tie = polygon([[-0.07, -0.15], [0.07, -0.15], [0.105, -0.5], [0, -0.64], [-0.105, -0.5]])

function Fabric({ shape, color, z }: { shape: THREE.Shape; color: string; z: number }) {
  return <mesh position={[0, 0, z]} castShadow>
    <extrudeGeometry args={[shape, { depth: 0.018, bevelEnabled: true, bevelSize: 0.008, bevelThickness: 0.008, bevelSegments: 1 }]} />
    <meshStandardMaterial color={color} roughness={0.94} side={THREE.DoubleSide} />
  </mesh>
}

function Whiskers({ side }: { side: -1 | 1 }) {
  return <group>
    {[-1, 0, 1].map((index) => <Stroke key={index} color="#ead9c3" width={0.004}
      points={[[side * 0.36, -0.24 + index * 0.035, 0.65],
        [side * 0.62, -0.22 + index * 0.07, 0.63],
        [side * 0.89, -0.25 + index * 0.13, 0.56]]} />)}
  </group>
}

function Otter({ active, pointer, motion, pose }: { active: boolean; pointer: RefObject<Pointer>; motion: boolean; pose: TaliPose }) {
  const body = useRef<THREE.Group>(null)
  const head = useRef<THREE.Group>(null)
  const rightArm = useRef<THREE.Group>(null)
  const leftArm = useRef<THREE.Group>(null)
  const leftFoot = useRef<THREE.Group>(null)
  const rightFoot = useRef<THREE.Group>(null)
  const tail = useRef<THREE.Group>(null)
  const eyes = useRef<THREE.Group>(null)
  const poseSince = useRef(0)
  const lastPose = useRef(pose)

  useFrame(({ clock }, delta) => {
    const t = clock.getElapsedTime()
    if (lastPose.current !== pose) { lastPose.current = pose; poseSince.current = t }
    const age = t - poseSince.current
    const ease = Math.min(delta * 6, 1)
    const walking = motion && pose === 'walk'
    const sleeping = motion && pose === 'sleep'
    const tired = motion && pose === 'tired'
    const slipping = motion && pose === 'slip'
    const step = Math.sin(t * 9)
    const slipWave = slipping ? Math.sin(Math.min(age / 4.6, 1) * Math.PI) : 0
    if (body.current) {
      const targetY = sleeping ? -0.26 : tired ? -0.18 : slipping ? -0.09 - slipWave * 0.18
        : walking ? -0.07 + Math.abs(step) * 0.09 : -0.09 + (motion ? Math.sin(t * 1.7) * 0.025 : 0)
      body.current.position.y = THREE.MathUtils.lerp(body.current.position.y, targetY, ease)
      const targetX = walking ? Math.sin(t * 1.15) * 0.19 : slipping ? slipWave * 0.15 : 0
      body.current.position.x = THREE.MathUtils.lerp(body.current.position.x, targetX, ease)
      const lean = sleeping ? -0.16 : tired ? 0.08 : slipping ? -slipWave * 0.58 : walking ? Math.sin(t * 4.5) * 0.07 : motion ? Math.sin(t * 0.75) * 0.015 : 0
      body.current.rotation.z = THREE.MathUtils.lerp(body.current.rotation.z, lean, ease)
    }
    if (head.current) {
      head.current.rotation.y = THREE.MathUtils.lerp(head.current.rotation.y, sleeping ? -0.1 : motion ? (pointer.current?.x ?? 0) * 0.2 : 0, ease)
      head.current.rotation.x = THREE.MathUtils.lerp(head.current.rotation.x, sleeping ? 0.2 : tired ? 0.16 : motion ? -(pointer.current?.y ?? 0) * 0.09 : 0, ease)
      head.current.rotation.z = THREE.MathUtils.lerp(head.current.rotation.z, sleeping ? -0.16 : tired ? 0.1 : motion ? Math.sin(t * 1.15) * 0.024 : 0, ease)
    }
    if (rightArm.current) rightArm.current.rotation.z = THREE.MathUtils.lerp(rightArm.current.rotation.z, walking ? step * 0.23 : sleeping ? 0.42 : tired ? -0.32 : motion && active ? -0.16 + Math.sin(t * 4.7) * 0.21 : -0.1, ease)
    if (leftArm.current) leftArm.current.rotation.z = THREE.MathUtils.lerp(leftArm.current.rotation.z, walking ? -step * 0.15 : sleeping ? -0.14 : 0.15, ease)
    if (leftFoot.current) leftFoot.current.rotation.x = THREE.MathUtils.lerp(leftFoot.current.rotation.x, walking ? step * 0.38 : slipping ? -slipWave * 0.6 : 0, ease)
    if (rightFoot.current) rightFoot.current.rotation.x = THREE.MathUtils.lerp(rightFoot.current.rotation.x, walking ? -step * 0.38 : slipping ? slipWave * 0.8 : 0, ease)
    if (tail.current) tail.current.rotation.y = motion ? Math.sin(t * (walking ? 5 : 1.8)) * (walking ? 0.28 : 0.16) : 0
    if (eyes.current) {
      const cycle = t % 5.7
      const blink = motion && ((cycle > 4.6 && cycle < 4.74) || (cycle > 4.86 && cycle < 4.96))
      eyes.current.scale.y = THREE.MathUtils.lerp(eyes.current.scale.y, sleeping || blink ? 0.06 : tired ? 0.56 : 1, Math.min(delta * 16, 1))
    }
  })

  return <group ref={body} position={[0, -0.09, 0]}>
    <group ref={tail} position={[-0.45, -0.85, -0.36]} rotation={[0.1, 0, 0.24]}>
      <Ball position={[-0.42, -0.14, 0]} scale={[0.58, 0.22, 0.24]} color={fur} />
      <Ball position={[-0.87, -0.25, 0.02]} scale={[0.37, 0.17, 0.18]} color={furLight} />
      <Ball position={[-1.12, -0.3, 0.06]} scale={[0.18, 0.1, 0.12]} color={furLight} />
    </group>
    <Ball position={[-0.27, -0.99, -0.02]} scale={[0.18, 0.27, 0.22]} color={navy} />
    <Ball position={[0.27, -0.99, -0.02]} scale={[0.18, 0.27, 0.22]} color={navy} />
    <group ref={leftFoot} position={[-0.32, -1.2, 0.1]}>
      <Ball position={[0, -0.07, 0.13]} scale={[0.27, 0.19, 0.36]} color={fur} />
      {[-0.12, 0, 0.12].map(x => <Ball key={x} position={[x, -0.15, 0.41]} scale={[0.075, 0.07, 0.12]} color={furLight} />)}
    </group>
    <group ref={rightFoot} position={[0.32, -1.2, 0.1]}>
      <Ball position={[0, -0.07, 0.13]} scale={[0.27, 0.19, 0.36]} color={fur} />
      {[-0.12, 0, 0.12].map(x => <Ball key={x} position={[x, -0.15, 0.41]} scale={[0.075, 0.07, 0.12]} color={furLight} />)}
    </group>
    <Ball position={[0, -0.72, -0.05]} scale={[0.57, 0.53, 0.46]} color={fur} />
    <Ball position={[0, -0.36, 0]} scale={[0.6, 0.67, 0.49]} color={navy} />
    <Ball position={[0, -0.77, 0.32]} scale={[0.41, 0.23, 0.22]} color={navyLight} />
    <Fabric shape={shirt} color="#f8f9f4" z={0.51} />
    <Fabric shape={leftLapel} color={navyLight} z={0.55} />
    <Fabric shape={rightLapel} color={navyLight} z={0.55} />
    <Fabric shape={tie} color={teal} z={0.61} />
    <Ball position={[0, -0.13, 0.64]} scale={[0.085, 0.07, 0.04]} color="#008c92" />
    <Ball position={[0.21, -0.65, 0.49]} scale={[0.035, 0.035, 0.017]} color="#ad865b" roughness={0.3} />
    <Ball position={[0.17, -0.85, 0.37]} scale={[0.035, 0.035, 0.017]} color="#ad865b" roughness={0.3} />
    <Stroke points={[[-0.48, -0.47, 0.32], [-0.42, -0.5, 0.42], [-0.32, -0.5, 0.48]]} color="#586a86" width={0.008} />
    <Stroke points={[[0.48, -0.47, 0.32], [0.42, -0.5, 0.42], [0.32, -0.5, 0.48]]} color="#586a86" width={0.008} />
    {/* An embroidered T on the blazer echoes the mark on the tablet. */}
    <group position={[0.36, -0.3, 0.43]}>
      <mesh><boxGeometry args={[0.13, 0.025, 0.014]} /><meshStandardMaterial color="#ccecea" /></mesh>
      <mesh position={[0, -0.052, 0]}><boxGeometry args={[0.025, 0.11, 0.014]} /><meshStandardMaterial color="#ccecea" /></mesh>
    </group>
    <group ref={leftArm} position={[-0.6, -0.37, 0.05]} rotation={[0, 0, 0.15]}>
      <Ball position={[-0.07, -0.18, 0]} scale={[0.22, 0.4, 0.24]} color={navy} />
      <Ball position={[-0.13, -0.53, 0.18]} scale={[0.19, 0.17, 0.18]} color={fur} />
    </group>
    <group ref={rightArm} position={[0.59, -0.33, 0.05]}>
      <Ball position={[0.08, -0.2, 0]} scale={[0.22, 0.4, 0.24]} color={navy} />
      <Ball position={[0.12, -0.53, 0.17]} scale={[0.19, 0.17, 0.18]} color={fur} />
    </group>
    {/* A real 3D tablet, held in front of the jacket. */}
    <group position={[-0.36, -0.52, 0.75]} rotation={[0, -0.14, 0.17]}>
      <mesh castShadow><boxGeometry args={[0.6, 0.82, 0.075]} /><meshStandardMaterial color="#333d50" metalness={0.38} roughness={0.46} /></mesh>
      <mesh position={[0, 0, 0.042]}><boxGeometry args={[0.52, 0.7, 0.012]} /><meshStandardMaterial color="#495267" roughness={0.35} /></mesh>
      <mesh position={[0, 0.08, 0.053]}><boxGeometry args={[0.16, 0.03, 0.008]} /><meshStandardMaterial color="#86f4e6" /></mesh>
      <mesh position={[0, -0.005, 0.053]}><boxGeometry args={[0.035, 0.17, 0.008]} /><meshStandardMaterial color="#86f4e6" /></mesh>
    </group>
    <Ball position={[-0.5, -0.78, 0.86]} scale={[0.18, 0.14, 0.15]} color={furLight} />
    <group ref={head} position={[0, 0.5, 0.06]}>
      <Ball position={[-0.52, 0.39, -0.06]} scale={[0.14, 0.15, 0.12]} color={fur} />
      <Ball position={[0.52, 0.39, -0.06]} scale={[0.14, 0.15, 0.12]} color={fur} />
      <Ball position={[-0.52, 0.4, 0.052]} scale={[0.075, 0.085, 0.035]} color="#d9987c" />
      <Ball position={[0.52, 0.4, 0.052]} scale={[0.075, 0.085, 0.035]} color="#d9987c" />
      <Ball position={[0, 0, 0]} scale={[0.7, 0.56, 0.55]} color={fur} />
      <Ball position={[0, 0.28, 0.27]} scale={[0.53, 0.23, 0.23]} color={furLight} />
      <Ball position={[-0.1, 0.53, 0.03]} scale={[0.13, 0.16, 0.12]} color={furLight} />
      <Ball position={[0.04, 0.55, 0.02]} scale={[0.12, 0.16, 0.11]} color={furLight} />
      <Ball position={[0.17, 0.5, 0.02]} scale={[0.09, 0.12, 0.09]} color={fur} />
      <Ball position={[0, -0.26, 0.34]} scale={[0.57, 0.25, 0.29]} color={cream} />
      <Ball position={[-0.21, -0.22, 0.52]} scale={[0.29, 0.18, 0.19]} color="#fce6c3" />
      <Ball position={[0.21, -0.22, 0.52]} scale={[0.29, 0.18, 0.19]} color="#fce6c3" />
      <Ball position={[0, -0.37, 0.5]} scale={[0.25, 0.1, 0.09]} color="#fce6c3" />
      <group ref={eyes}>
        {([-1, 1] as const).map(side => <group key={side}>
          <Ball position={[side * 0.24, 0.1, 0.49]} scale={[0.155, 0.18, 0.085]} color={furDark} />
          <Ball position={[side * 0.24, 0.1, 0.552]} scale={[0.135, 0.155, 0.055]} color="#fff7ec" roughness={0.26} />
          <Ball position={[side * 0.24 - 0.015, 0.075, 0.603]} scale={[0.083, 0.103, 0.034]} color="#603d32" roughness={0.14} />
          <Ball position={[side * 0.24 - 0.018, 0.07, 0.631]} scale={[0.05, 0.073, 0.02]} color="#211d20" roughness={0.08} />
          <Ball position={[side * 0.24 - 0.045, 0.12, 0.649]} scale={[0.021, 0.027, 0.009]} color="white" roughness={0.1} />
        </group>)}
      </group>
      <Stroke points={[[-0.37, 0.32, 0.49], [-0.26, 0.35, 0.52], [-0.16, 0.33, 0.5]]} color={furDark} width={0.018} />
      <Stroke points={[[0.16, 0.33, 0.5], [0.26, 0.35, 0.52], [0.37, 0.32, 0.49]]} color={furDark} width={0.018} />
      <group visible={pose === 'sleep'}>
        <Stroke points={[[-0.4, 0.09, 0.63], [-0.24, 0.035, 0.68], [-0.09, 0.09, 0.63]]} color={furDark} width={0.012} />
        <Stroke points={[[0.09, 0.09, 0.63], [0.24, 0.035, 0.68], [0.4, 0.09, 0.63]]} color={furDark} width={0.012} />
      </group>
      <Ball position={[0, -0.14, 0.68]} scale={[0.12, 0.07, 0.08]} color="#3d3032" roughness={0.33} />
      <Stroke points={[[0, -0.19, 0.74], [0, -0.28, 0.7]]} color="#8b5947" width={0.01} />
      <Stroke points={[[-0.16, -0.28, 0.66], [-0.08, -0.34, 0.69], [0, -0.35, 0.7], [0.08, -0.34, 0.69], [0.16, -0.28, 0.66]]} color="#8b5947" width={0.011} />
      {([-1, 1] as const).map(side => <group key={side}>
        <Ball position={[side * 0.34, -0.25, 0.68]} scale={[0.012, 0.012, 0.012]} color="#9c7260" />
        <Ball position={[side * 0.39, -0.22, 0.66]} scale={[0.01, 0.01, 0.01]} color="#9c7260" />
      </group>)}
      <Whiskers side={-1} /><Whiskers side={1} />
    </group>
  </group>
}

export function TaliPet({ active, pointer, motion, pose }: { active: boolean; pointer: RefObject<Pointer>; motion: boolean; pose: TaliPose }) {
  return <Canvas dpr={[1, 2]} camera={{ position: [0, 0.19, 4.5], fov: 40 }} gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}>
    <ambientLight intensity={0.92} />
    <directionalLight position={[-2, 4, 5]} intensity={2.15} color="#fff1dc" />
    <directionalLight position={[3, 1, -2]} color="#b0f6ed" intensity={1.05} />
    <pointLight position={[0, -1, 3]} color="#dffaff" intensity={0.34} />
    <Otter active={active} pointer={pointer} motion={motion} pose={pose} />
  </Canvas>
}
