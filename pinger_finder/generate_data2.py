import numpy as np
import acoustics
from environment import hydrophones, tools3d, source 

# ############################
##### Init Functions ########
############################

def load_matplotlib():
    # Load modules
    print("Loading Matplotlib library...")
    import matplotlib
#    matplotlib.use('GTK')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    
    # Configure settings
    print("...done.")

    return plt
    
def init_3D_plotting_view(ax):
    # Hold for multiple object plotting
    ax.hold(True)
    
    # Set Plotting limits
    lim = 50
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)
    ax.autoscale(False)

# ############################
## Graphics Functions #######
############################

def plot_contour(contour_obj, ax):
    o = contour_obj
    ax.plot_wireframe(o.X, o.Y, o.Z, rstride=1, cstride=1, color=np.random.rand(3,1))
    
def plot_object(obj, ax):
    o = obj
    ax.scatter(o.X,o.Y,o.Z,c='y')
    
# ############################
##### World Class ###########
############################
class World(object):
    # Initialize single objects
    env = tools3d.Environment()
    pinger = tools3d.Phys_Obj()
    array = hydrophones.Array()
    array.define(np.array([
        [-15e-3,0,(-15e-3)/2],
        [ 15e-3,0,(-15e-3)/2], 
        [     0,0,(15e-3)/2]
    ]))
    
    # Initialize grouped objects
    pinger_contour = []
    hydrophone = []
    for i in range(array.n_elements):
        pinger_contour.append(source.Pinger_Contour())
        hydrophone.append(tools3d.Phys_Obj())
        
    
    
    def __init__(self, ax=None):
        # Initialize axes and plotting object
        self.ax = ax
        self.hlocs = self.array.element_pos
        
        
    def reset_objects(self):
        # Move pinger to some place in the world
        self.pinger.move(np.array([[20,30,-5]]))
        

    def update_pinger_measurement(self):
        time_vals = acoustics.generate_arrival_times(self.env, self.array, 
            self.pinger)

        # plot something
        self.array.bulk_compute_ab_from_distances(time_vals*self.env.c)
    
        for idx in range(self.array.n_elements):
            ab = (self.array.ab[idx][0], self.array.ab[idx][1])
            self.pinger_contour[idx].coe_generate_contour(ab, idx, self.array)
    
            #pinger_contour.xform_rotate(np.array([[0,np.pi/3,0]]))
            plot_contour(self.pinger_contour[idx], self.ax)
        
            self.hydrophone[idx].move(self.array.element_pos[idx])
            plot_object(self.hydrophone[idx], self.ax)     
    
class Worldmember(object):
    pass
    
# ###########################
########## Main Program ####
###########################

def simulate_pinger_location():
    # Initializing graphics backend
    plt = load_matplotlib()
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    init_3D_plotting_view(ax)
    
    # Initializing world
    world = World(ax)
    
    # Plug pinger location in the evironment
    world.reset_objects()
    
    # Update pinger measurement
    world.update_pinger_measurement()
    
    plt.show()
    
simulate_pinger_location()
