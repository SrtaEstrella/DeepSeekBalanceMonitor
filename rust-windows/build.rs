use std::{
    env, fs,
    path::{Path, PathBuf},
    process::{Command, Stdio},
};

fn main() {
    println!("cargo:rerun-if-changed=app.manifest");
    println!("cargo:rerun-if-changed=app.ico");

    let target = env::var("TARGET").unwrap_or_default();
    if !target.contains("windows-msvc") {
        return;
    }

    let manifest = PathBuf::from(
        env::var_os("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR must be set by Cargo"),
    )
    .join("app.manifest");
    let icon = manifest
        .parent()
        .expect("manifest path must have a parent")
        .join("app.ico");

    let host = env::var("HOST").unwrap_or_default();
    if host.contains("windows") {
        compile_resources(&manifest, &icon).expect("failed to compile Windows resources");
    } else {
        println!("cargo:rustc-link-arg-bins=/MANIFEST:EMBED");
        println!(
            "cargo:rustc-link-arg-bins=/MANIFESTINPUT:{}",
            manifest.display()
        );
    }
}

fn compile_resources(manifest: &Path, icon: &Path) -> Result<(), String> {
    let out_dir = PathBuf::from(env::var_os("OUT_DIR").ok_or("OUT_DIR is not set")?);
    let rc_path = out_dir.join("app.rc");
    let res_path = out_dir.join("app.res");
    fs::write(
        &rc_path,
        format!(
            "1 ICON \"{}\"\n1 24 \"{}\"\n",
            resource_path(icon),
            resource_path(manifest)
        ),
    )
    .map_err(|e| e.to_string())?;

    let compiler = find_resource_compiler().ok_or("rc.exe or llvm-rc.exe was not found")?;
    let status = Command::new(compiler)
        .arg("/nologo")
        .arg(format!("/fo{}", res_path.display()))
        .arg(&rc_path)
        .status()
        .map_err(|e| e.to_string())?;
    if !status.success() {
        return Err(format!("{compiler} exited with {status}"));
    }

    println!("cargo:rustc-link-arg-bins={}", res_path.display());
    Ok(())
}

fn resource_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn find_resource_compiler() -> Option<&'static str> {
    ["rc.exe", "llvm-rc.exe", "rc", "llvm-rc"]
        .into_iter()
        .find(|&compiler| {
            Command::new(compiler)
                .arg("/?")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .is_ok()
        })
}
