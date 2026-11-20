import { Canvas, useFrame } from '@react-three/fiber'
import { useRef, type RefObject } from 'react'
import * as THREE from 'three'

type Pointer = { x: number; y: number }

const fur = '#a86d4f'
const furLight = '#c18a65'
const cream = '#f5d9ae'
const navy = '#253451'
const navyLight = '#354765'
const teal = '#03b7ad'

function Ball({ position, scale, color, roughness = 0.85 }: {
  position: [number, number, number]; scale: [number, number, number]; color: string; roughness?: number
}) {
  return <mesh position={position} scale={scale} castShadow receiveShadow>
    <sphereGeometry args={[1, 32, 24]} />
    <meshStandardMaterial color={color} roughness={roughness} />
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
    {[-0.1, 0, 0.1].map((offset, index) => <mesh key={index}
      position={[side * 0.67, -0.2 + offset, 0.53]}
      rotation={[0, 0, Math.PI / 2 + side * offset * 1.9]}>
      <cylinderGeometry args={[0.0045, 0.0045, 0.34, 5]} />
      <meshStandardMaterial color="#e8d6bc" />
    </mesh>)}
  </group>
}

function Otter({ active, pointer, motion }: { active: boolean; pointer: RefObject<Pointer>; motion: boolean }) {
  const body = useRef<THREE.Group>(null)
  const head = useRef<THREE.Group>(null)
  const rightArm = useRef<THREE.Group>(null)
  const tail = useRef<THREE.Group>(null)
  const eyes = useRef<THREE.Group>(null)

  useFrame(({ clock }, delta) => {
    const t = clock.getElapsedTime()
    const ease = Math.min(delta * 5, 1)
    if (body.current) {
      body.current.position.y = motion ? Math.sin(t * 1.7) * 0.03 : 0
      body.current.rotation.z = motion ? Math.sin(t * 0.75) * 0.018 : 0
    }
    if (head.current) {
      head.current.rotation.y = THREE.MathUtils.lerp(head.current.rotation.y, (pointer.current?.x ?? 0) * 0.23, ease)
      head.current.rotation.x = THREE.MathUtils.lerp(head.current.rotation.x, -(pointer.current?.y ?? 0) * 0.1, ease)
      head.current.rotation.z = motion ? Math.sin(t * 1.15) * 0.035 : 0
    }
    if (rightArm.current) rightArm.current.rotation.z = motion && active ? -0.12 + Math.sin(t * 5) * 0.27 : -0.1
    if (tail.current) tail.current.rotation.y = motion ? Math.sin(t * 1.8) * 0.17 : 0
    if (eyes.current) {
      const cycle = t % 5.7
      const blink = motion && ((cycle > 4.6 && cycle < 4.72) || (cycle > 4.83 && cycle < 4.91))
      eyes.current.scale.y = THREE.MathUtils.lerp(eyes.current.scale.y, blink ? 0.08 : 1, Math.min(delta * 22, 1))
    }
  })

  return <group ref={body} position={[0, -0.09, 0]}>
    <group ref={tail} position={[-0.45, -0.85, -0.36]} rotation={[0.1, 0, 0.24]}>
      <Ball position={[-0.55, -0.14, 0]} scale={[0.72, 0.2, 0.21]} color={fur} />
      <Ball position={[-1.09, -0.19, 0]} scale={[0.2, 0.12, 0.13]} color={furLight} />
    </group>
    <Ball position={[-0.32, -1.11, 0.17]} scale={[0.29, 0.17, 0.35]} color={fur} />
    <Ball position={[0.32, -1.11, 0.17]} scale={[0.29, 0.17, 0.35]} color={fur} />
    <Ball position={[0, -0.72, -0.05]} scale={[0.57, 0.53, 0.46]} color={fur} />
    <Ball position={[0, -0.36, 0]} scale={[0.6, 0.67, 0.49]} color={navy} />
    <Fabric shape={shirt} color="#f8f9f4" z={0.51} />
    <Fabric shape={leftLapel} color={navyLight} z={0.55} />
    <Fabric shape={rightLapel} color={navyLight} z={0.55} />
    <Fabric shape={tie} color={teal} z={0.61} />
    <Ball position={[0, -0.13, 0.64]} scale={[0.085, 0.07, 0.04]} color="#008c92" />
    <Ball position={[0.21, -0.65, 0.49]} scale={[0.035, 0.035, 0.017]} color="#ad865b" roughness={0.3} />
    <Ball position={[0.17, -0.85, 0.37]} scale={[0.035, 0.035, 0.017]} color="#ad865b" roughness={0.3} />
    {/* An embroidered T on the blazer echoes the mark on the tablet. */}
    <group position={[0.36, -0.3, 0.43]}>
      <mesh><boxGeometry args={[0.13, 0.025, 0.014]} /><meshStandardMaterial color="#ccecea" /></mesh>
      <mesh position={[0, -0.052, 0]}><boxGeometry args={[0.025, 0.11, 0.014]} /><meshStandardMaterial color="#ccecea" /></mesh>
    </group>
    <group position={[-0.6, -0.37, 0.05]} rotation={[0, 0, 0.15]}>
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
      <Ball position={[-0.5, 0.38, -0.07]} scale={[0.14, 0.16, 0.13]} color={fur} />
      <Ball position={[0.5, 0.38, -0.07]} scale={[0.14, 0.16, 0.13]} color={fur} />
      <Ball position={[-0.5, 0.39, 0.05]} scale={[0.07, 0.09, 0.035]} color="#d9aa8c" />
      <Ball position={[0.5, 0.39, 0.05]} scale={[0.07, 0.09, 0.035]} color="#d9aa8c" />
      <Ball position={[0, 0, 0]} scale={[0.65, 0.53, 0.53]} color={fur} />
      <Ball position={[-0.09, 0.49, 0]} scale={[0.12, 0.14, 0.1]} color={furLight} />
      <Ball position={[0.06, 0.51, 0.02]} scale={[0.1, 0.13, 0.1]} color={furLight} />
      <Ball position={[0, -0.2, 0.4]} scale={[0.52, 0.3, 0.22]} color={cream} />
      <Ball position={[-0.18, -0.23, 0.59]} scale={[0.22, 0.14, 0.1]} color="#ffe9c6" />
      <Ball position={[0.18, -0.23, 0.59]} scale={[0.22, 0.14, 0.1]} color="#ffe9c6" />
      <group ref={eyes}>
        {([-1, 1] as const).map(side => <group key={side}>
          <Ball position={[side * 0.245, 0.08, 0.48]} scale={[0.14, 0.17, 0.075]} color="#fff4df" roughness={0.3} />
          <Ball position={[side * 0.245 + 0.015, 0.07, 0.552]} scale={[0.077, 0.1, 0.045]} color="#291e21" roughness={0.12} />
          <Ball position={[side * 0.245 - 0.012, 0.12, 0.591]} scale={[0.025, 0.028, 0.012]} color="white" roughness={0.1} />
        </group>)}
      </group>
      <Ball position={[-0.25, 0.3, 0.44]} scale={[0.14, 0.03, 0.025]} color="#684736" />
      <Ball position={[0.25, 0.3, 0.44]} scale={[0.14, 0.03, 0.025]} color="#684736" />
      <Ball position={[0, -0.15, 0.67]} scale={[0.14, 0.085, 0.075]} color="#403038" roughness={0.38} />
      <mesh position={[0, -0.29, 0.675]} rotation={[0, 0, Math.PI]}>
        <torusGeometry args={[0.08, 0.01, 8, 20, Math.PI]} />
        <meshStandardMaterial color="#8b5947" />
      </mesh>
      <Whiskers side={-1} /><Whiskers side={1} />
    </group>
  </group>
}

export function TaliPet({ active, pointer, motion }: { active: boolean; pointer: RefObject<Pointer>; motion: boolean }) {
  return <Canvas dpr={[1, 1.5]} camera={{ position: [0, 0.22, 4.5], fov: 40 }} gl={{ alpha: true, antialias: true, powerPreference: 'low-power' }}>
    <ambientLight intensity={1.5} />
    <directionalLight position={[-2, 4, 5]} intensity={2.1} />
    <directionalLight position={[3, 1, -2]} color="#9cefeb" intensity={1.2} />
    <Otter active={active} pointer={pointer} motion={motion} />
  </Canvas>
}
