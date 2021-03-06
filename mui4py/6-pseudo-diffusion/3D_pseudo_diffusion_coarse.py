"""
#
#% @file 3D_pseudo_diffusion_coarse.py
#% @author W.L.
#% @date 21 Nov 2019
#% @brief See README.md
#
"""

from mpi4py import MPI
import mpi4py
import datetime
import numpy as np
import time
import os

# Include MUI header file and configure file 
import mui4py

# Common world claims 
MPI_COMM_WORLD = mui4py.mpi_split_by_app()

# Declare MPI ranks
rank = MPI_COMM_WORLD.Get_rank()

# Define MUI dimension
dimensionMUI = 2

# Define the name of push/fetch values
name_push = "coarseField"
name_fetch  = "fineField"

# Define MUI push/fetch data types
data_types_push = {name_push: mui4py.FLOAT64}
data_types_fetch = {name_fetch: mui4py.FLOAT64} 

# MUI interface creation
domain = "coarseDomain"
config2d = mui4py.Config(dimensionMUI, mui4py.FLOAT64)
iface = ["interface2D01", "interface2D02"]
MUI_Interfaces = mui4py.create_unifaces(domain, iface, config2d) 
MUI_Interfaces["interface2D01"].set_data_types(data_types_fetch)
MUI_Interfaces["interface2D02"].set_data_types(data_types_push)

print("mpi4py.get_config(): ", mpi4py.get_config(), "\n")
print("mui4py.get_compiler_config(): ", mui4py.get_compiler_config(), "\n")
print("mui4py.get_compiler_version(): ", mui4py.get_compiler_version(), "\n")
print("mui4py.get_mpi_version(): ", mui4py.get_mpi_version(), "\n")

# Define the forget steps of MUI to reduce the memory
forgetSteps = int(5)

# Define the search radius of the RBF sampler
# The search radius should not set to a very large value so that to ensure a good convergence
rSampler = 0.4

# Define parameters of the RBF sampler
cutoff = 1e-9
iConservative = False
iPolynomial = True
iReadMatrix = False
rbfMatrixFolder="rbfCoarse"

# Create the RBF Matrix Folder includes all intermediate folders if don't exists
if not os.path.exists(rbfMatrixFolder):
    os.makedirs(rbfMatrixFolder)
    print("Folder " , rbfMatrixFolder, " created ")
else:
    print("Folder " , rbfMatrixFolder,  " already exists")

# Setup diffusion rate
dr = 0.5

# Setup time steps
steps = int(200)

# Setup output interval
outputInterval  = int(1)

# Geometry info
# origin coordinate (x-axis direction) of the geometry
x0 = 1.0
# origin coordinate (y-axis direction) of the geometry
y0 = 0.0
# origin coordinate (z-axis direction) of the geometry
z0 = 0.0
# length (x-axis direction) of the geometry
lx = 1.0
# length (y-axis direction) of the geometry
ly = 1.0
# length (z-axis direction) of the geometry
lz = 1.0

# Domain discretization
# number of grid points in x axis
Ni = int(9)
# number of grid points in y axis
Nj = int(9)
# number of grid points in z axis
Nk = int(9)
# total number of points
Npoints = Ni*Nj*Nk

# Tolerance of data points
tolerance = (lx/(Ni-1))*0.5

# Store point coordinates
points = np.zeros((Npoints, 3))
c_0 = 0
for k in range(Nk):
    for j in range(Nj):
        for i in range(Ni):
            points[c_0] = [(x0+(lx/(Ni-1))*i), (y0+(ly/(Nj-1))*j), (z0+(lz/(Nk-1))*k)]
            c_0 += 1

# Generate initial pseudo scalar field
scalar_field = np.zeros(Npoints)
for i in range(Npoints):
    scalar_field[i] = 0.0

# Declare list to store mui::point2d
point2dList = []

# Store mui::point2d that located in the fetch interface
c_0 = 0
for k in range(Nk):
    for j in range(Nj):
        for i in range(Ni):
            if ((points[c_0][0]-x0) <= tolerance):
                point_fetch = MUI_Interfaces["interface2D01"].Point([points[c_0][1], points[c_0][2]])
                point2dList.append(point_fetch)
            c_0 += 1

# Define and announce MUI send/receive span
send_span = mui4py.geometry.Box([y0, z0], [(y0+ly), (z0+lz)])
recv_span = mui4py.geometry.Box([y0, z0], [(y0+ly), (z0+lz)])
MUI_Interfaces["interface2D01"].announce_recv_span(0, (steps+1), recv_span)
MUI_Interfaces["interface2D02"].announce_send_span(0, (steps+1), send_span)

# Spatial/temporal samplers
t_sampler = mui4py.ChronoSamplerExact()
s_sampler = mui4py.SamplerRbf(rSampler, point2dList, iConservative, cutoff, iPolynomial, rbfMatrixFolder, iReadMatrix)

# Commit ZERO step
MUI_Interfaces["interface2D02"].commit(0)

# Output the initial pseudo scalar field
outputFileName = "coupling_results/scalar_field_coarse_0.csv"
outputFile = open(outputFileName,"w+")
outputFile.write("\"X\",\"Y\",\"Z\",\"scalar_field\"\n")
c_0 = 0
for k in range(Nk):
    for j in range(Nj):
        for i in range(Ni):
            outputFile.write("%f,%f,%f,%f\n" % (points[c_0][0],points[c_0][1],points[c_0][2],scalar_field[c_0]))
            c_0 += 1
outputFile.close() 

# Declare integrations of the pseudo scalar field at boundaries
# Integration of the pseudo scalar field at the left boundary of Domain 2
intFaceLD2 = 0.0
# Integration of the pseudo scalar field at the right boundary of Domain 2
intFaceRD2 = 0.0

# Define output files for boundary integrations
outputIntegrationName = "coupling_results/faceIntegrationD2.txt"
outputIntegration = open(outputIntegrationName,"w+")
outputIntegration.write("\"t\",\"intFaceLD2\",\"intFaceRD2\"\n")
outputIntegration.close()

# Begin time loops
for t in range(1, (steps+1)):

    print("\n")
    print("{Coarse Domain} ", t," Step \n")

    # Reset boundary integrations
    intFaceLD2 = 0.0
    intFaceRD2 = 0.0

    # Loop over points of Domain 2
    c_0 = 0
    for k in range(Nk):
        for j in range(Nj):
            for i in range(Ni):
                # Loop over left boundary points of Domain 2
                if ((points[c_0][0]-x0) <= tolerance):
                    points_fetch = [points[c_0][1], points[c_0][2]]
                    # Fetch data from the other solver
                    scalar_field[c_0] = MUI_Interfaces["interface2D01"].\
                                                        fetch(name_fetch,
                                                        points_fetch,
                                                        t,
                                                        s_sampler,
                                                        t_sampler)

                    # Calculate the integration of left boundary points of Domain 2
                    intFaceLD2 += scalar_field[c_0]
                else: # Loop over 'internal' points of Domain 2

                    #Calculate the diffusion of pseudo scalar field of Domain 2
                    scalar_field[c_0] += dr*(scalar_field[c_0 - 1] - scalar_field[c_0])

                    # Loop over right boundary points of Domain 2
                    if (( (x0+lx) - points[c_0][0]) <= (tolerance)):
                        points_push = [(y0+(ly/(Nj-1))*j), (z0+(lz/(Nk-1))*k)]
                        # push data to the other solver
                        MUI_Interfaces["interface2D02"].push(name_push, points_push, scalar_field[c_0])
                        # Calculate the integration of right boundary points of Domain 2
                        intFaceRD2 += scalar_field[c_0]
                c_0 += 1

    # Commit 't' step of MUI
    MUI_Interfaces["interface2D02"].commit(t)

    # Forget data from Zero step to 't - forgetSteps' step of MUI to save memory
    if ( (t - forgetSteps) > 0 ):
        MUI_Interfaces["interface2D02"].forget(t - forgetSteps)

    # Output the pseudo scalar field and the boundary integrations
    if ((t % outputInterval) == 0):
        outputFileName = "coupling_results/scalar_field_coarse_" + str(t) + ".csv"
        outputFile = open(outputFileName,"w+")
        outputFile.write("\"X\",\"Y\",\"Z\",\"scalar_field\"\n")
        c_0 = 0
        for k in range(Nk):
            for j in range(Nj):
                for i in range(Ni):
                    outputFile.write("%f,%f,%f,%f\n" % (points[c_0][0],points[c_0][1],points[c_0][2],scalar_field[c_0]))
                    c_0 += 1

        outputFile.close() 

        outputIntegration = open(outputIntegrationName,"a")
        outputIntegration.write("%i,%f,%f\n" % (t,intFaceLD2,intFaceRD2))
        outputIntegration.close()