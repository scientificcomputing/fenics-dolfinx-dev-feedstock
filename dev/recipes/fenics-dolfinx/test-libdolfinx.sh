#!/usr/bin/env bash
set -ex
pkg-config --libs dolfinx

# not sure why this custom command isn't run by cmake
ffcx cpp/test/poisson.py -o cpp/test

# disable clang availability check
if [[ "$target_platform" =~ "osx" ]]; then
  export CXXFLAGS="${CXXFLAGS} -D_LIBCPP_DISABLE_AVAILABILITY"
  # jthread with clang 19 is behind a flag
  export CXXFLAGS="${CXXFLAGS} -fexperimental-library"
fi

if [[ "$target_platform" =~ "linux" ]]; then
  # array bounds check seems to be needed for some versions of gcc
  # (only linux cross-compile at the moment)
  # ref: https://github.com/FEniCS/dolfinx/pull/3216/files#diff-1bba462ab050e89360fd88110a689e85ee037749cea091a1848ab574381d3795R260-R265
  export CXXFLAGS="${CXXFLAGS} -Wno-array-bounds"
fi
# The library is built in Release mode (NDEBUG), which compiles out the
# precondition checks in e.g. IndexMap.cpp. The tests guard the matching
# CHECK_THROWS with #ifndef NDEBUG, so build them with NDEBUG too; otherwise
# "IndexMap preconditions" expects exceptions that are never thrown.
export CXXFLAGS="${CXXFLAGS} -DNDEBUG"

# Keep UCX on shared memory and TCP; otherwise it may try the GitHub ARM
# runner's Azure NIC (mana_0) and MPI_Init fails with
# "uct_iface_open(ud_verbs/mana_0:1) failed: Address not valid".
export UCX_TLS=self,sm,tcp

export CMAKE_GENERATOR=Ninja

cmake -DCMAKE_BUILD_TYPE=Developer -B build-test/ -S cpp/test/
cmake --build build-test --parallel "${CPU_COUNT:-1}" --verbose
cd build-test

ctest -V --output-on-failure -R unittests
