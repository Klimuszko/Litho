import {useEffect, useRef} from "react";
import * as THREE from "three";
import {OrbitControls} from "three/examples/jsm/controls/OrbitControls.js";
import {STLLoader} from "three/examples/jsm/loaders/STLLoader.js";


export default function ScadPreview({url}: {url: string | null}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!host.current) return;
    const element = host.current;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x111722);
    const camera = new THREE.PerspectiveCamera(42, 1, .1, 10000);
    camera.position.set(90, 70, 110);
    const renderer = new THREE.WebGLRenderer({antialias: true});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x253047, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 2.5); key.position.set(4, 7, 5); scene.add(key);
    const floor = new THREE.GridHelper(240, 24, 0x46556f, 0x273246); floor.position.y = -1; scene.add(floor);

    let mesh: THREE.Mesh | null = null;
    if (url) new STLLoader().load(url, geometry => {
      geometry.computeVertexNormals();
      geometry.center();
      geometry.computeBoundingBox();
      const box = geometry.boundingBox || new THREE.Box3();
      const size = box.getSize(new THREE.Vector3());
      geometry.rotateX(-Math.PI / 2);
      mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({color: 0xf0b247, roughness: .68, metalness: .04}));
      mesh.castShadow = true; scene.add(mesh);
      const longest = Math.max(size.x, size.y, size.z, 1);
      camera.near = longest / 100; camera.far = longest * 20;
      camera.position.set(longest * 1.2, longest * .9, longest * 1.45);
      camera.updateProjectionMatrix(); controls.target.set(0, 0, 0); controls.update();
    });

    const resize = () => {
      const width = element.clientWidth || 640, height = element.clientHeight || 500;
      renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize); observer.observe(element); resize();
    let frame = 0;
    const draw = () => { controls.update(); renderer.render(scene, camera); frame = requestAnimationFrame(draw); }; draw();
    return () => {
      cancelAnimationFrame(frame); observer.disconnect(); controls.dispose(); renderer.dispose();
      mesh?.geometry.dispose(); (mesh?.material as THREE.Material | undefined)?.dispose();
      renderer.domElement.remove();
    };
  }, [url]);

  return <div className="scad-preview" ref={host}>{!url && <div className="scad-preview-empty"><b>Podgląd 3D</b><span>Zmień parametry i kliknij „Generuj”</span></div>}</div>;
}
