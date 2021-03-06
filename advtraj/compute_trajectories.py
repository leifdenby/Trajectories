# -*- coding: utf-8 -*-
import os

from netCDF4 import Dataset
import numpy as np
from scipy import ndimage
from sklearn.cluster import KMeans
from scipy.optimize import minimize
#import matplotlib.pyplot as plt

L_vap = 2.501E6
Cp = 1005.0
L_over_cp = L_vap / Cp
R_air = 287.058
r_over_cp = R_air/Cp
grav = 9.81
mol_wt_air        =           28.9640
mol_wt_water      =           18.0150
epsilon           = mol_wt_water/mol_wt_air
c_virtual         = 1.0/epsilon-1.0

#debug_unsplit = True
debug_unsplit = False
#debug_label = True  
debug_label = False  
#debug_mean = True 
debug_mean = False 
#debug = True
debug = False

cyclic_xy = True
#use_bilin = False
use_bilin = True

class Trajectory_Family : 
    """
    Class defining a family of back trajectories. 
    
    This is an ordered list of trajectories with sequential reference times.
    
    Args:
        files             : ordered list of files used to generate trajectories                            
        ref_prof_file     : name of file containing reference profile.
        first_ref_time    : Time of reference.
        last_ref_time     : Time of reference.
        back_len          : Time to go back from ref.
        forward_len       : Time to go forward from ref.
        deltax            : Model x grid spacing in m.
        deltay            : Model y grid spacing in m.
        deltaz            : Model z grid spacing in m. 
        variable_list=None: List of variable names for data to interpolate to trajectory.                              
        ref_func          : function to return reference trajectory positions and labels.
        in_obj_func       : function to determine which points are inside an object.
        kwargs            : any additional keyword arguments to ref_func (dict).
    
    Attributes:
        family(list): List of trajectory objects with required reference times.
    
    @author: Peter Clark
    
    """
    
    def __init__(self, files, ref_prof_file, \
                 first_ref_time, last_ref_time, \
                 back_len, forward_len, \
                 deltax, deltay, deltaz, \
                 ref_func, in_obj_func, kwargs={}, variable_list=None) : 
        """
        Create an instance of a family of back trajectories.

        @author: Peter Clark
            
        """

        self.family = list([]) 
        
        first_ref_file, it, delta_t = find_time_in_files(files, \
                                                    first_ref_time)
        dataset=Dataset(files[first_ref_file])
#        print(first_ref_file, it, delta_t)
        if delta_t > 0.0 :                  
            dataset.close()
            print(\
            'Starting trajectory family calculation at time {} in file {}'.\
            format(first_ref_time,files[first_ref_file]))
            print('Time step is {}'.format(delta_t))
        else :
            return
        
        for ref in np.arange(first_ref_time, last_ref_time+delta_t, delta_t):
            print('Trajectories for reference time {}'.format(ref))
            start_time = ref - back_len
            end_time = ref + forward_len  

            traj = Trajectories(files, ref_prof_file, \
                                start_time, ref, end_time, \
                                deltax, deltay, deltaz, \
                                ref_func, in_obj_func, kwargs=kwargs, \
                                variable_list=variable_list) 
            self.family.append(traj)
#            input("Press a key")
        return
    
    def matching_object_list(self, master_ref = None, select = None ):
        """
        Method to generate a list of matching objects at all times they match. 
        Matching is done using overlap of in_obj boxes.

        Args:
            master_ref=None  : Which trajectory set in family to use to find matching objects. Default is the last set.
            select=None      : Which objects to find matches for.
        
        Returns:        
            dictionary pointing to arrays of mean properties and meta data::
        
                Dictionary keys::
                  "master_ref"       : master_ref actually used.
                  "objects"          : object numbers selected.
                  "matching_objects" : List described below.
                  
            List with one member for each trajectory set with an earlier 
            reference time than master_ref. 
            
            By default, this is all the sets apart 
            from the last. Let us say t_off is the backwards offset from the
            reference time, with t_off=0 for the time immediately before the
            reference time.
            
            Each member is a list with one member for each back trajectory time 
            in the master_ref trajectories, containing a list with one member for 
            every object in master_ref,comprising an array of integer indices of the 
            matching objects in the earlier set that match the reference object
            at the given time. This may be empty if no matches have been found.
            Let us say the it_back measures the time backwards from master_ref, with
            it_back=0 at the reference time.
            
            Thus, if mol is the matching object list,
            mol[t_off][it_back][iobj] is an array of object ids belonging to
            trajectory set master_ref-(t_off+1), at master_ref trajectory time it_back before 
            the master_ref reference time and matching object index iobj a the reference time.
            
        @author: Peter Clark
        
        """
        
        mol = list([])
        if master_ref is None : master_ref = len(self.family) - 1
        traj = self.family[master_ref]
        if select is None : select = np.arange(0, traj.nobjects, dtype = int)
        # Iterate backwards from first set before master_ref.
        for t_off in range(0, master_ref) :
            # We are looking for objects in match_traj matching those in traj.
            match_traj = self.family[master_ref-(t_off+1)]
            # matching_objects[t_off] will be those objects in match_traj 
            # which match traj at any time.
            matching_objects = list([])

            # Iterate backwards over all set times from master_ref to start. 
            for it_back in range(0,traj.ref+1) :
                # Time to make comparison
                ref_time = traj.ref-it_back
                # Note match_traj.ref in general will equal traj.ref 
                # Time in match_traj that matches ref_time
                #       so match_time = master_ref - it_back
                match_time = match_traj.ref + (t_off + 1)- it_back 
                matching_object_at_time = list([])

                # Iterate over objects in master_ref.
                for iobj in select :

                    if traj.num_in_obj[ref_time ,iobj] > 0 :
                        b_test = traj.in_obj_box[ref_time, iobj,...]

                        # Find boxes in match_traj at match_time that overlap
                        # in_obj box for iobj at the same time.
                        if (match_time >= 0) & \
                          (match_time < np.shape(match_traj.in_obj_box)[0]) :

                            b_set  = match_traj.in_obj_box[match_time,...]
                            corr_box = box_overlap_with_wrap(b_test, b_set, \
                                traj.nx, traj.ny)
                            valid = (match_traj.num_in_obj[match_time, corr_box]>0)
                            corr_box = corr_box[valid]
                    matching_object_at_time.append(corr_box)
                matching_objects.append(matching_object_at_time)
            mol.append(matching_objects)
        ret_dict = {"master_ref": master_ref, "objects": select, "matching_objects": mol}
        return ret_dict
   
    def print_matching_object_list(self, master_ref = None, select = None) :    
        """
        Method to print matching object list.
        
        See method matching_object_list.
        
        @author: Peter Clark
        
        """
        
        if master_ref == None : master_ref = len(self.family) - 1
        if select is None : select = np.arange(0, self.family[master_ref].nobjects, \
                                           dtype = int)
        mol_dict = self.matching_object_list(master_ref = master_ref, select = select)
        mol = mol_dict["matching_objects"]
#        for t_off in range(0, 4) :
        for t_off in range(0, len(mol)) :
            matching_objects = mol[t_off]
            for i in range(0, len(select)) :
                iobj = select[i]
                for it_back in range(0, len(matching_objects)) :
#                for it_back in range(0, 4) :
                    rep =""
                    for obj in matching_objects[it_back][i] :
                        rep += "{} ".format(obj)
                    if len(rep) > 0 :
                        print("t_off: {0} iobj: {1} it_back: {2} obj: {3}".\
                                  format(t_off, iobj, it_back, rep))
        return
    
    def matching_object_list_summary(self, master_ref = None, select = None, \
                                     overlap_thresh=0.02) :
        """
        Method to classify matching objects.
        
        Args: 
            master_ref=None  : Which trajectory set in family to use to find \
             matching objects. Default is the last set.         
            overlap_thresh=0.02 Threshold for overlap to be sufficient for inclusion.
            
                          
        Returns:
            Dictionary pointing to arrays of mean properties and meta data::
        
                Dictionary keys::
                  "master_ref"              : master_ref actually used.
                  "objects"                 : object numbers selected.
                  "matching_object_summary" : List described below.
                  
            List with one member for each trajectory set with an earlier reference than master_ref. 
            
            By default, this is all the sets apart from the last.
            
            Each member is a list with one member for each object in master_ref,
            containing a list of objects in the earlier set that match the
            object in master_ref AT ANY TIME.
            
            Each of these is classified 'Linked' if the object is in the 
            max_at_ref list at the earler reference time, otherwise 'Same'.
            
        @author: Peter Clark
        
        """
        
        if master_ref is None : master_ref = len(self.family) - 1
        traj = self.family[master_ref]
        if select is None : select = np.arange(0, traj.nobjects, dtype = int )
        mol_dict = self.matching_object_list(master_ref = master_ref, select=select)        
        mol = mol_dict["matching_objects"]
        mols = list([])
        # Iterate backwards from first set before master_ref.
        for t_off, matching_objects in enumerate(mol) :
            match_list = list([])
#            match_time = master_ref-(t_off+1)
                # Note match_traj.ref in general will equal traj.ref 
                # Time in match_traj that matches ref_time
                 #       so match_time = master_ref - it_back
            for i, iobj in enumerate(select) :
                objlist = list([])
                otypelist = list([])
                interlist = list([])
                for it_back in range(0, len(matching_objects)) :
                    match_traj = self.family[master_ref-(t_off+1)]
                    ref_time = traj.ref-it_back
                    match_time = match_traj.ref + (t_off + 1)- it_back 
#                    print('times',ref_time,match_time)
                    if (match_time >= 0) & (match_time < len(self.family)) :
                        for obj in matching_objects[it_back][i] :
                            if np.size(obj) > 0 :
                        
                                if obj not in objlist : 
                                
                                    inter = self.refine_object_overlap(t_off, \
                                            it_back, iobj, obj, master_ref = master_ref)
                                
                                    if inter > overlap_thresh :
                                
                                        otype = 'Same'
                                        if obj in \
                                            match_traj.max_at_ref :
                                                otype = 'Linked'
                                        objlist.append(obj)
                                        otypelist.append(otype)
                                        interlist.append(int(round(inter*100,0)))
                match_list.append(list(zip(objlist,otypelist,interlist)))
            mols.append(match_list)
        ret_dict = {"master_ref": master_ref, "objects": select, "matching_object_summary": mols}
        return ret_dict
    
    def print_matching_object_list_summary(self, master_ref = None,  select = None, \
                                           overlap_thresh = 0.02) :    
        """
        Method to print matching object list summary.
        
        See method matching_object_list_summary.
        
        @author: Peter Clark
        
        """
        
        if master_ref is None : master_ref = len(self.family) - 1
        if select is None : select = np.arange(0, self.family[master_ref].nobjects, \
                                               dtype = int)
        mols_dict = self.matching_object_list_summary(master_ref = master_ref, select = select, \
                                                 overlap_thresh = overlap_thresh)
        mols = mols_dict["matching_object_summary"]
        for t_off in range(0, len(mols)) :
            matching_objects = mols[t_off]
            for i in range(0, len(select)) :
                iobj = select[i]
                rep =""
                for mo, mot, mint in matching_objects[i] : 
                    rep += "({}, {}, {:02d})".format(mo,mot,mint)
                if len(rep) > 0 :
                    print("t_off: {0} iobj: {1} obj: {2} ".\
                                  format(t_off, iobj, rep))
                           
        return

    def find_linked_objects(self, master_ref = None, select = None, \
        overlap_thresh = 0.02) :   
        """
        Method to find all objects linked to objects in max_at_ref list in master_ref.
        
        Args: 
            master_ref=None      : Which trajectory set in family to use to find matching objects. Default is the last set.                         
            overlap_thresh=0.02  : Threshold for overlap to be sufficient for inclusion.
                          
        Returns:
            List with one member for each object in max_at_ref list in master_ref.
            Each member is a an array of triplets containing the time,
            object id and percentage ovelap with next of objects in the 
            max_at_ref list of the family at time classified as 'Linked'.
            
        @author: Peter Clark
        
        """
        
        if master_ref is None : master_ref = len(self.family) - 1
        if select is None : select = self.family[master_ref].max_at_ref
        mols_dict = self.matching_object_list_summary(master_ref = master_ref, select = select, \
                                                 overlap_thresh = overlap_thresh)
        mols = mols_dict["matching_object_summary"]
        linked_objects = list([])
        for i in range(len(select)) :
            linked_obj = list([])
            linked_obj.append([master_ref, select[i], 100])
            for t_off in range(0, len(mols)) :
                matching_objects = mols[t_off][i]
                for mo, mot, mint in matching_objects : 
                    if mot == 'Linked' :
                        linked_obj.append([master_ref-t_off-1, mo, mint])
            linked_objects.append(np.array(linked_obj))
        return linked_objects
    
    def print_linked_objects(self, master_ref = None, select = None, \
                             overlap_thresh = 0.02) :
        """
        Method to print linked object list.
        
        See method find_linked_objects.
        
        @author: Peter Clark
        
        """
        
        if master_ref == None : master_ref = len(self.family) - 1
        if select is None : select = self.family[master_ref].max_at_ref
        linked_objects = self.find_linked_objects(master_ref = master_ref, select=select, \
                                                  overlap_thresh = \
                                                  overlap_thresh)
        for iobj, linked_obj in zip(select, \
                                    linked_objects) :
            rep =""
 #           for t_off, mo in linked_obj : 
            for i in range(np.shape(linked_obj)[0]) :
                t_off, mo, mint = linked_obj[i,:]  
                rep += "[{}, {}, {}]".format(t_off, mo, mint)
            print("iobj: {0} objects: {1} ".format(iobj, rep))
        return
    
    def find_super_objects(self, master_ref = None, \
        overlap_thresh = 0.02) :
        """
        Method to find all objects linked contiguously to objects in max_at_ref list in master_ref.
        
        Args: 
            master_ref=None           : Which trajectory set in family to use to find matching objects. Default is the last set.                                           
            overlap_thresh=0.02: Threshold for overlap to be sufficient for inclusion.
                          
        Returns:
            super_objects, len_sup
            
            super_objects is a list with one member for each object in max_at_ref list in master_ref.
            Each member is an array of triplets containing the time,
            object id and percentage ovelap with next of objects in the 
            max_at_ref list of the family at time classified as 'Linked'.
            
            len_sup is an array of the lengths of each super_objects array
            
        @author: Peter Clark
        
        """
        
        def step_obj_back(master_ref, objs) :
            found_super_objs = list([])
            mol_dict = self.matching_object_list(master_ref = master_ref, select=objs)        
            mol = mol_dict["matching_objects"]
            t_off = 0
            matching_objects = mol[t_off]
            match_time = master_ref-(t_off+1)
            for i,iobj in enumerate(objs) :
                objlist = list([(master_ref,iobj,100)])
                it_back = 0
#                print(iobj)
#                print(master_ref,match_time, matching_objects[it_back][i])
                for obj in matching_objects[it_back][i] :
                    if np.size(obj) > 0 :
                                
                        inter = self.refine_object_overlap(t_off, \
                                    it_back, iobj, obj, master_ref = master_ref)
#                        print(obj,inter)        
                        if inter > overlap_thresh :
                            if obj in self.family[master_ref-(t_off+1)].max_at_ref :
                                objlist.append((match_time,obj,\
                                                int(inter*100+0.5)))
#                                print(objlist)
            
                found_super_objs.append(objlist)
            return found_super_objs
            
        print("Finding super-objects")
        if master_ref is None : master_ref = len(self.family) - 1
        select = self.family[master_ref].max_at_ref
        super_objects = list([])
        incomplete_objects = list([])
        incomplete_object_ids = np.array([],dtype=int)
        for newref in range(master_ref,0,-1) :
            sup_obj = step_obj_back(newref, select)
            next_level_objs = self.family[newref-1].max_at_ref
            new_incomplete_objects = list([])
            new_incomplete_object_ids = list([])
            for i, obj in enumerate(sup_obj) :
                # Four options
                # 1. New object length 1.
                # 2. Termination of previous object.
                # 3. New object continued at next level.
                # 4. Continuation of previous object.
                if len(obj) == 1 :
                    if obj[0][1] in incomplete_object_ids :
                        # Terminate incomplete object.
                        j = np.where(obj[0][1] == incomplete_object_ids)[0][0]
                        super_objects.append(np.array(incomplete_objects[j]))
                    else :
                        super_objects.append(np.array(obj))
                else :
                    if obj[0][1] in incomplete_object_ids :
                        j = np.where(obj[0][1] == incomplete_object_ids)[0][0]
                        incomplete_objects[j].append(obj[1])
                        new_incomplete_objects.append(incomplete_objects[j]) 
                    else :
                        new_incomplete_objects.append(obj) 
                        
                    new_incomplete_object_ids.append(\
                        new_incomplete_objects[-1][-1][1])
            incomplete_object_ids = np.array(new_incomplete_object_ids)           
            incomplete_objects = new_incomplete_objects
            select = next_level_objs  
            
        for obj in incomplete_objects : super_objects.append(np.array(obj))  
        len_sup=[]
        for s in super_objects : len_sup.append(len(s))
        len_sup = np.array(len_sup)
                         
        return super_objects, len_sup
           
    def refine_object_overlap(self, t_off, time, obj, mobj, master_ref=None) :
        """
        Method to estimate degree of overlap between two trajectory objects.
            Reference object is self.family trajectory object obj at time master_ref-time
            Comparison object is self.family trajectory object mobj 
            at same true time, reference time master_ref-(t_off+1).
        
        Args: 
            t_off(integer)    : Reference object is at time index master_ref-time
            time(integer)     : Comparison object is at time index master_ref-(t_off+1)
            obj(integer)      : Reference object id
            mobj(integer)     : Comparison object if.
            master_ref=None(integer) : default is last set in family.
                           
        Returns: 
            Fractional overlap
            
        @author: Peter Clark
        
        """
        
        if master_ref == None : master_ref = len(self.family) - 1
#        print(t_off, time, obj, mobj)
#        print("Comparing trajectories {} and {}".format(master_ref, master_ref-(t_off+1)))
        
        def extract_obj_as1Dint(fam, master_ref, time, obj) :
            traj = fam[master_ref]
            tr_time = traj.ref-time
#            print("Time in {} is {}, {}".format(master_ref, tr_time, traj.times[tr_time]))
            obj_ptrs = (traj.labels == obj)
#            print('extr',master_ref, time, tr_time)
            mask, objvar = traj.in_obj_func(traj, tr_time, obj_ptrs, \
                                            **traj.ref_func_kwargs)
#            mask = mask[tr_time, obj_ptrs]
#            print(np.shape(mask))
            tr = (traj.trajectory[tr_time, obj_ptrs, ... ] + 0.5).astype(int)
#            print(np.shape(tr))
            tr = tr[mask,:]
#            for i in range(2) : print(np.min(tr[:,i]),np.max(tr[:,i]))
            tr1D = np.unique(tr[:,0] + traj.nx * (tr[:,1] + traj.ny * tr[:,2]))
            return tr1D
#        traj = self.family[master_ref]
#        match_traj = self.family[master_ref-(t_off+1)]
#        ref_time = traj.ref-it_back
#        match_time = match_traj.ref + (t_off + 1)- it_back 
            
    
        tr1D  = extract_obj_as1Dint(self.family, master_ref,           \
                                    time, obj)
        trm1D = extract_obj_as1Dint(self.family, master_ref-(t_off+1), \
                                    time-(t_off+1) , mobj)
                
        max_size = np.max([np.size(tr1D),np.size(trm1D)])
        if max_size > 0 :
            intersection = np.size(np.intersect1d(tr1D,trm1D))/max_size
        else :
            intersection = 0
        return intersection
            
    def __str__(self):
        rep = "Trajectories family\n"
        for tr in self.family :
            rep += tr.__str__()
        return rep
           
    def __repr__(self):
        rep = "Trajectories family\n"
        for tr in self.family :
            rep += tr.__repr__()
        return rep

class Trajectories :
    """
    Class defining a set of back trajectories with a given reference time. 
    
    This is an ordered list of trajectories with sequential reference times.
    
    Args:
        files              : ordered list of files used to generate trajectories                            
        ref_prof_file      : name of file containing reference profile.
        start_time         : Time for origin of back trajectories.
        ref                : Reference time of trajectories.
        end_time           : Time for end of forward trajectories.
        deltax             : Model x grid spacing in m.
        deltay             : Model y grid spacing in m.
        deltaz             : Model z grid spacing in m. 
        variable_list=None : List of variable names for data to interpolate to trajectory.                              
        ref_func           : function to return reference trajectory positions and labels.
        in_obj_func        : function to determine which points are inside an object.
        kwargs             : any additional keyword arguments to ref_func (dict).
    
    Attributes:
    
        rhoref (array): Reference profile of density.
        pref (array): Reference profile of pressure.
        thref (array): Reference profile of potential temperature.
        piref (array): Reference profile of Exner pressure.
        data : Array [nt, m, n] where nt is total number of times, 
            m the number of trajectory points at a given time and 
            n is the number of variables in variable_list.
        trajectory: Array [nt, m, 3] where the last index gives x,y,z 
        traj_error: Array [nt, m, 3] with estimated error in trajectory.
        traj_times: Array [nt] with times corresponding to trajectory.
        labels: Array [m] labelling points with labels 0 to nobjects-1. 
        nobjects: Number of objects.
        xcoord: xcoordinate of model space.
        ycoord: ycoordinate of model space.
        zcoord: zcoordinate of model space.
        deltat: time spacing in trajectories.
        ref_func           : function to return reference trajectory positions and labels.
        in_obj_func        : function to determine which points are inside an object.
        ref_func_kwargs: any additional keyword arguments to ref_func (dict).
        files: Input file list.
        ref: Index of reference time in trajectory array.
        end: Index of end time in trajectory array. (start is always 0)
        ntimes: Number of times in trajectory array.
        npoints: Number of points in trajectory array.
        deltax             : Model x grid spacing in m.
        deltay             : Model y grid spacing in m.
        deltaz             : Model z grid spacing in m. 
        nx: length of xcoord
        ny: length of xcoord
        nz: length of xcoord
        variable_list: variable_list corresponding to data.
        trajectory: trajectory array.        
        data_mean: mean of in_obj points data.
        num_in_obj: number of in_obj points.
        centroid: centroid of in_objy points
        bounding_box: box containing all trajectory points.
        in_obj_box: box containing all in_obj trajectory points.
        max_at_ref: list of objects which reach maximum LWC at reference time.

    @author: Peter Clark
    
    """

    def __init__(self, files, ref_prof_file, start_time, ref, end_time, \
                 deltax, deltay, deltaz, \
                 ref_func, in_obj_func, kwargs={}, variable_list=None ) : 
        """
        Create an instance of a set of trajectories with a given reference. 
 
        This is an ordered list of trajectories with sequential reference times.
                    
        @author: Peter Clark

        """

        if variable_list == None : 
            variable_list = { \
                  "u":r"$u$ m s$^{-1}$", \
                  "v":r"$v$ m s$^{-1}$", \
                  "w":r"$w$ m s$^{-1}$", \
                  "th":r"$\theta$ K", \
                  "p":r"Pa", \
                  "q_vapour":r"$q_{v}$ kg/kg", \
                  "q_cloud_liquid_mass":r"$q_{cl}$ kg/kg", \
                  }
                  
        dataset_ref = Dataset(ref_prof_file)

        self.rhoref = dataset_ref.variables['rhon'][-1,...]
        self.pref = dataset_ref.variables['prefn'][-1,...]
        self.thref = dataset_ref.variables['thref'][-1,...]
        self.piref = (self.pref[:]/1.0E5)**r_over_cp
        self.data, trajectory, self.traj_error, self.times, self.ref, \
        self.labels, self.nobjects, \
        self.xcoord, self.ycoord, self.zcoord, self.deltat = \
        compute_trajectories(files, start_time, ref, end_time, \
                             variable_list.keys(), self.thref, \
                             ref_func, kwargs=kwargs) 
        self.ref_func=ref_func
        self.in_obj_func=in_obj_func
        self.ref_func_kwargs=kwargs
        self.files = files
#        self.ref   = (ref-start_time)//self.deltat
        self.end = len(self.times)-1
        self.ntimes = np.shape(trajectory)[0]
        self.npoints = np.shape(trajectory)[1]
        self.deltax = deltax
        self.deltay = deltay
        self.deltaz = deltaz
        self.nx = np.size(self.xcoord)
        self.ny = np.size(self.ycoord)
        self.nz = np.size(self.zcoord)
        self.variable_list = variable_list
        self.trajectory = unsplit_objects(trajectory, self.labels, \
                                          self.nobjects, self.nx, self.ny)        
        self.data_mean, self.in_obj_data_mean, self.objvar_mean, \
            self.num_in_obj, \
            self.centroid, self.in_obj_centroid, self.bounding_box, \
            self.in_obj_box = compute_traj_boxes(self, in_obj_func, \
                                                kwargs=kwargs)

        max_objvar = (self.objvar_mean == np.max(self.objvar_mean, axis=0))
        when_max_objvar = np.where(max_objvar)
        self.max_at_ref = when_max_objvar[1][when_max_objvar[0] == self.ref]
        return
        
    def var(self, v) :
        """
        Method to convert variable name to numerical pointer. 

        Args:
            v (string):  variable name.

        Returns:
            Numerical pointer to data in data array.

        @author: Peter Clark

        """

        i = list(self.variable_list.keys()).index(v)
        
        for ii, vr in enumerate(list(self.variable_list)) :
            if vr==v : break
        if ii != i : print("var issue: ", self.variable_list.keys(), v, i, ii)
        return ii
    
    def select_object(self, iobj) :
        """
        Method to find trajectory and associated data corresponding to iobj.

        Args:
            iobj(integer) : object id .

        Returns:
            trajectory_array, associated _data.

        @author: Peter Clark

        """

        in_object = (self.labels == iobj)
        obj = self.trajectory[:, in_object, ...]
        dat = self.data[:, in_object, ...]
        return obj, dat
    
    def __str__(self):
        rep = "Trajectories centred on reference Time : {}\n".\
        format(self.times[self.ref])
        rep += "Times : {}\n".format(self.ntimes)
        rep += "Points : {}\n".format(self.npoints)
        rep += "Objects : {}\n".format(self.nobjects)
        return rep
           
    def __repr__(self):
        rep = "Trajectory Reference time: {0}, Times:{1}, Points:{2}, Objects:{3}\n".format(\
          self.times[self.ref],self.ntimes,self.npoints, self.nobjects)
        return rep

        
def dict_to_index( v) :
    """
    Method to convert variable name to numerical pointer. 

    Args:
        v (string):  variable name.

    Returns:
        Numerical pointer to data in data array.

    @author: Peter Clark

    """

    raise NotImplementedError("LD: `self` varible below doesn't exist here")
    ii = list(self.variable_list.keys()).index(v)  # noqa

#    for ii, vr in enumerate(list(self.variable_list)) :
#        if vr==v : break
    return ii
    
def compute_trajectories(files, start_time, ref_time, end_time, \
                         variable_list, thref, ref_func, kwargs={}) :
    """
    Function to compute forward and back trajectories plus associated data.
        
    Args: 
        files         : Ordered list of netcdf files containing 3D MONC output.
        start_time    : Time corresponding to end of back trajectory.
        ref_time      : Time at which reference objects are defined.
        end_time      : Time corresponding to end of forward trajectory.
        variable_list : List of variables to interpolate to trajectory points.
        thref         : theta_ref profile.

    Returns:
        Set of variables defining trajectories::
        
            data_val: Array [nt, m, n] where nt is total number of times, 
                m the number of trajectory points at a given time and 
                n is the number of variables in variable_list.
            trajectory: Array [nt, m, 3] where the last index gives x,y,z 
            traj_error: Array [nt, m, 3] with estimated error in trajectory.
            traj_times: Array [nt] with times corresponding to trajectory.
            labels: Array [m] labelling points with labels 0 to nobjects-1. 
            nobjects: Number of objects.
            xcoord: xcoordinate of model space.
            ycoord: ycoordinate of model space.
            zcoord: zcoordinate of model space.
            deltat: time spacing in trajectories.
           
    @author: Peter Clark
        
    """
    
    print('Computing trajectories from {} to {} with reference {}.'.\
          format(start_time, end_time, ref_time))
    
    ref_file_number, ref_time_index, delta_t = find_time_in_files(\
                                                        files, ref_time)
    
    dataset=Dataset(files[ref_file_number])
    theta = dataset.variables["th"]
    ref_times = dataset.variables[theta.dimensions[0]][...]
    print('Starting in file number {}, name {}, index {} at time {}.'.\
          format(ref_file_number, os.path.basename(files[ref_file_number]), \
                 ref_time_index, ref_times[ ref_time_index] ))
    file_number = ref_file_number
    time_index = ref_time_index
    
    # Find initial positions and labels using user-defined function.
    traj_pos, labels, nobjects = ref_func(dataset, time_index, **kwargs)

    times = ref_times
#    print(time_index)
#    input("Press enter")
    trajectory, data_val, traj_error, traj_times, xcoord, ycoord, zcoord \
      = trajectory_init(dataset, time_index, variable_list, thref, traj_pos)
#    input("Press enter")
    ref_index = 0
    
    print("Computing backward trajectories.")
    
    while (traj_times[0] > start_time) and (file_number >= 0) :
        time_index -= 1
        if time_index >= 0 :
            print('Time index: {} File: {}'.format(time_index, \
                   os.path.basename(files[file_number])))
            trajectory, data_val, traj_error, traj_times = \
            back_trajectory_step(dataset, time_index, variable_list, thref, \
                               xcoord, ycoord, zcoord, \
                               trajectory, data_val, traj_error, traj_times)
            ref_index += 1
        else :
            file_number -= 1
            if file_number < 0 :
                print('Ran out of data.')
            else :                
                dataset.close()
                print('File {} {}'.format(file_number, \
                      os.path.basename(files[file_number])))
                dataset = Dataset(files[file_number])
                theta = dataset.variables["th"]
                times = dataset.variables[theta.dimensions[0]][...]
                time_index = len(times)
    dataset.close()
    
# Back to reference time for forward trajectories.
    file_number = ref_file_number
    time_index = ref_time_index
    times = ref_times
    dataset = Dataset(files[ref_file_number])

    print("Computing forward trajectories.")
         
    while (traj_times[-1] < end_time) and (file_number >= 0) :
        time_index += 1
        if time_index < len(times) :
            print('Time index: {} File: {}'.format(time_index, \
                   os.path.basename(files[file_number])))
            trajectory, data_val, traj_error, traj_times = \
                forward_trajectory_step(dataset, time_index, \
                                        variable_list, thref, \
                                        xcoord, ycoord, zcoord, \
                                        trajectory, data_val,  traj_error, \
                                        traj_times)
        else :
            file_number += 1
            if file_number == len(files) :
                print('Ran out of data.')
            else :                
                dataset.close()
                print('File {} {}'.format(file_number, \
                      os.path.basename(files[file_number])))
                dataset = Dataset(files[file_number])
                theta = dataset.variables["th"]
                times = dataset.variables[theta.dimensions[0]][...]
                time_index = -1
    dataset.close()
          
    print('data_val: {} {} {}'.format( len(data_val), len(data_val[0]), \
          np.size(data_val[0][0]) ) )
          
    data_val = np.reshape(np.vstack(data_val), \
               (len(data_val), len(data_val[0]), np.size(data_val[0][0]) ) )
    
    print('trajectory: {} {} {}'.format(len(trajectory[1:]), len(trajectory[0]), \
                               np.size(trajectory[0][0])))
    print('traj_error: {} {} {}'.format(len(traj_error[1:]), len(traj_error[0]), \
                               np.size(traj_error[0][0])))
#    print np.shape()

    trajectory = np.reshape(np.vstack(trajectory[1:]), \
               ( len(trajectory[1:]), len(trajectory[0]), \
                 np.size(trajectory[0][0]) ) ) 
    
    traj_error = np.reshape(np.vstack(traj_error[1:]), \
               ( len(traj_error[1:]), len(traj_error[0]), \
                 np.size(traj_error[0][0]) ) ) 
    
    traj_times = np.reshape(np.vstack(traj_times),-1)
    
    return data_val, trajectory, traj_error, traj_times, ref_index, \
      labels, nobjects, \
      xcoord, ycoord, zcoord, delta_t

def extract_pos(nx, ny, dat) :
    """
    Function to extract 3D position from data array.

    Args:
        nx        : Number of points in x direction.
        ny        : Number of points in y direction.
        dat       : Array[m,n] where n>=5 if cyclic_xy or 3 if not.

    Returns: 
        pos       : Array[m,3]
        n_pvar    : Number of dimensions in input data used for pos.
    """
    
    global cyclic_xy
    if cyclic_xy :
        n_pvar = 5
        xpos = phase(dat[0],dat[1],nx)
        ypos = phase(dat[2],dat[3],ny)     
        pos = np.array([xpos, ypos, dat[4]]).T
    else :
        n_pvar = 3
        pos = np.array([dat[0], dat[1], dat[2]]).T
        
    return pos, n_pvar
    
    
def trajectory_init(dataset, time_index, variable_list, thref, traj_pos) :
    """
    Function to set up origin of back and forward trajectories.

    Args:
        dataset       : Netcdf file handle.
        time_index    : Index of required time in file.
        variable_list : List of variable names.
        thref         : array with reference theta profile.
        traj_pos      : array[n,3] of initial 3D positions.

    Returns: 
        Trajectory variables::
        
            trajectory     : position of origin point.
            data_val       : associated data so far.
            traj_error     : estimated trajectory errors so far. 
            traj_times     : trajectory times so far.
            xcoord         : 1D array giving x coordinate space of data.
            ycoord         : 1D array giving y coordinate space of data.
            zcoord         : 1D array giving z coordinate space of data.

    @author: Peter Clark

    """
    
    
    data_list, time = load_traj_step_data(dataset, time_index, variable_list, \
                                          thref)
    print("Starting at time {}".format(time))
    
    (nx, ny, nz) = np.shape(data_list[0])
    
    xcoord = np.arange(nx ,dtype='float')
    ycoord = np.arange(ny, dtype='float')
    zcoord = np.arange(nz, dtype='float')
    
    out = data_to_pos(data_list, traj_pos, xcoord, ycoord, zcoord)

    traj_pos_new, n_pvar = extract_pos(nx, ny, out)
#    print data_list

#    data_val = list([])
#    for data in data_list[n_pvar:]:
#        data_val.append(data[logical_pos])
#    data_val=[np.vstack(data_val).T]
    
    data_val = list([np.vstack(out[n_pvar:]).T])
    
    if debug :
        raise NotImplementedError("LD: `variable` below doesn't exist here")
        print('Value of {} at trajectory position.'.format(variable))  # noqa
        print(np.shape(data_val))
        print(np.shape(traj_pos))
        print('xorg',traj_pos[:,0])
        print('yorg',traj_pos[:,1])
        print('zorg',traj_pos[:,2])
        print('x',traj_pos_new[:,0])
        print('y',traj_pos_new[:,1])
        print('z',traj_pos_new[:,2])
        
    trajectory = list([traj_pos])
    traj_error = list([np.zeros_like(traj_pos)])
    trajectory.insert(0,traj_pos_new)
    traj_error.insert(0,np.zeros_like(traj_pos_new))
    traj_times = list([time])
#    print 'init'
#    print 'trajectory:',len(trajectory[:-1]), len(trajectory[0]), np.size(trajectory[0][0])
#    print 'traj_error:',len(traj_error[:-1]), len(traj_error[0]), np.size(traj_error[0][0])
    
    return trajectory, data_val, traj_error, traj_times, xcoord, ycoord, zcoord

def back_trajectory_step(dataset, time_index, variable_list, thref, \
                         xcoord, ycoord, zcoord, \
                         trajectory, data_val, traj_error, traj_times) :
    """
    Function to execute backward timestep of set of trajectories.
    
    Args: 
        dataset        : netcdf file handle.
        time_index     : time index in netcdf file.
        variable_list  : list of variable names.
        thref          : array with reference theta profile.
        xcoord, ycoord, zcoord: 1D arrays giving coordinate spaces of data.
        trajectory     : trajectories so far. trajectory[0] is position of earliest point.                             
        data_val       : associated data so far.
        traj_error     : estimated trajectory errors to far. 
        traj_times     : trajectory times so far.

    Returns:    
        Inputs updated to new location::
        
            trajectory, data_val, traj_error, traj_times
        
    @author: Peter Clark
    
    """
        
    data_list, time = load_traj_step_data(dataset, time_index, variable_list, \
                                          thref)
    print("Processing data at time {}".format(time))
    
    (nx, ny, nz) = np.shape(data_list[0])
    
    traj_pos = trajectory[0]
#    print "traj_pos ", np.shape(traj_pos), traj_pos[:,0:5]
    
    out = data_to_pos(data_list, traj_pos, xcoord, ycoord, zcoord)

    traj_pos_new, n_pvar = extract_pos(nx, ny, out)

    data_val.insert(0, np.vstack(out[n_pvar:]).T)       
    trajectory.insert(0, traj_pos_new)  
    traj_error.insert(0, np.zeros_like(traj_pos_new))
    traj_times.insert(0, time)

    return trajectory, data_val, traj_error, traj_times
    
def forward_trajectory_step(dataset, time_index, variable_list, thref, \
                            xcoord, ycoord, zcoord, \
                            trajectory, data_val, traj_error, traj_times) :    
    """
    Function to execute forward timestep of set of trajectories.
    
    Args: 
        dataset        : netcdf file handle.
        time_index     : time index in netcdf file.
        variable_list  : list of variable names.
        thref          : array with reference theta profile.
        xcoord, ycoord, zcoord: 1D arrays giving coordinate spaces of data.
        trajectory     : trajectories so far. trajectory[-1] is position of latest point.
        data_val       : associated data so far.
        traj_error     : estimated trajectory errors to far. 
        traj_times     : trajectory times so far.

    Returns: 
        Inputs updated to new location::
        
            trajectory, data_val, traj_error, traj_times
        
    @author: Peter Clark
        
    """
            
    data_list, time = load_traj_step_data(dataset, time_index, variable_list, \
                                          thref)
    print("Processing data at time {}".format(time))
    
    (nx, ny, nz) = np.shape(data_list[0])
    
    traj_pos = trajectory[-1]
    traj_pos_next_est = 2*trajectory[0]-trajectory[1]
  
#    traj_pos_next_est = 60.0*np.array([1/100., 1/100., 1/40.])[:,None]*traj_pos*data_val[0][:,2]
#    traj_pos_est = trajectory[1]
    
#    print "traj_pos ", np.shape(traj_pos), traj_pos#[:,0:5]
#    print "traj_pos_prev ",np.shape(trajectory[1]), trajectory[1]#[:,0:5]
    def print_info(kk):
        print('kk = {} Error norm :{} Error :{}'.format(kk, mag_diff[kk], \
              diff[:,kk]))
        print('Looking for at this index ', \
              [traj_pos[:,m][kk] for m in range(3)])
        print('Nearest solution for the index', \
              [traj_pos_at_est[kk,m] for m in range(3)])
        print('Located at ', \
              [traj_pos_next_est[kk,m] for m in range(3)])
        return
    
    def int3d_dist(pos) :
#    global dist_data
        if np.size(np.shape(pos)) == 1 :
           pos = np.atleast_2d(pos).T

        out = np.max([0,ndimage.map_coordinates(dist_data, pos, \
                                                mode='nearest', order=2)])
#   out = ndimage.map_coordinates(dist_data, pos, mode='nearest', order=2)
#   print ('out = {}'.format(out))
        return out
    
    err = 1.0
    niter = 0 
    max_iter = 30
    errtol_iter = 1E-4
    errtol = 5E-3
    relax_param = 0.5
    not_converged = True
    correction_cycle = False 
    while not_converged : 
        out = data_to_pos(data_list, traj_pos_next_est, \
                                  xcoord, ycoord, zcoord)

        traj_pos_at_est, n_pvar = extract_pos(nx, ny, out)

#        print("traj_pos_at_est ", np.shape(traj_pos_at_est), traj_pos_at_est)#[:,0:5]
        diff = traj_pos_at_est - traj_pos
        
# Deal with wrap around.
        
        traj_pos_at_est[:,0][diff[:,0]<(-nx/2)] += nx
        diff[:,0][diff[:,0]<(-nx/2)] += nx
        traj_pos_at_est[:,0][diff[:,0]>=(nx/2)] -= nx
        diff[:,0][diff[:,0]>=(nx/2)] -= nx
        traj_pos_at_est[:,1][diff[:,1]<-(ny/2)] += ny
        diff[:,1][diff[:,1]<-(ny/2)] += ny
        traj_pos_at_est[:,1][diff[:,1]>=(ny/2)] -= ny
        diff[:,1][diff[:,1]>= (ny/2)] -= ny
        
        mag_diff = 0
        for i in range(3):
            mag_diff += diff[i,:]**2
            
        err = np.max(mag_diff)
        
        if correction_cycle :
            print('After correction cycle {}'.format(err))
            if debug :
                try: 
                    k
                    for kk in k :
                        print_info(kk)

                except NameError:
                    print('No k')
            break
        
        if err <= errtol_iter :
            not_converged = False
            print(niter, err)
           
        if niter <= max_iter :
#            traj_pos_prev_est = traj_pos_next_est
#            traj_pos_at_prev_est = traj_pos_at_est
            traj_pos_next_est = traj_pos_next_est - diff * relax_param
            niter +=1
        else :   
            print('Iterations exceeding {} {}'.format(max_iter, err))
            if err > errtol :
                bigerr = (mag_diff > errtol)    
                if np.size(diff[:,bigerr]) > 0 :
                    k = np.where(bigerr)[0]
                    if debug :
                        print('Index list into traj_pos_at_est is {}'.format(k))
                    for kk in k :
                        if debug :
                            print_info(kk)            
                        lx = np.int(np.round(traj_pos_next_est[kk,0]))
                        ly = np.int(np.round(traj_pos_next_est[kk,1]))
                        lz = np.int(np.round(traj_pos_next_est[kk,2]))
                        if debug :
                            print('Index in source array is {},{},{}'.\
                                  format(lx,ly,lz))
                        
                        nd = 5
                        
                        xr = np.arange(lx-nd,lx+nd+1, dtype=np.intp) % nx
                        yr = np.arange(ly-nd,ly+nd+1, dtype=np.intp) % ny
                        zr = np.arange(lz-nd,lz+nd+1, dtype=np.intp)
                        
                        zr[zr >= nz] = nz-1
                        zr[zr <  0 ] = 0
                        
                        x_real = data_list[0]
                        x_imag = data_list[1]
                        y_real = data_list[2]
                        y_imag = data_list[3]
                        z_dat   = data_list[4]
        
                        xpos = phase(x_real[np.ix_(xr,yr,zr)],\
                                     x_imag[np.ix_(xr,yr,zr)],nx)
                        ypos = phase(y_real[np.ix_(xr,yr,zr)],\
                                     y_imag[np.ix_(xr,yr,zr)],ny)
                        zpos = z_dat[np.ix_(xr,yr,zr)]
                        
                        dx = xpos - traj_pos[:,0][kk]
                        dy = ypos - traj_pos[:,1][kk]
                        dz = zpos - traj_pos[:,2][kk]
                        dx[dx >= (nx/2)] -= nx
                        dx[dx < (-nx/2)] += nx
                        dy[dy >= (ny/2)] -= ny
                        dy[dy < (-ny/2)] += ny
                                               
                        dist = dx**2 + dy**2 +dz**2
                                                        
                        lp = np.where(dist == np.min(dist))
                        
                        lxm = lp[0][0]
                        lym = lp[1][0]
                        lzm = lp[2][0]

                        if debug :
                            print('Nearest point is ({},{},{},{})'.\
                                  format(lxm,lym,lzm, dist[lxm,lym,lzm]))
                            print(xpos[lxm,lym,lzm],ypos[lxm,lym,lzm],zpos[lxm,lym,lzm])
#                            ix = (lx+lxm-nd)%nx
#                            iy = (ly+lym-nd)%ny
#                            print(phase(x_real[ix, iy, lz+lzm-nd],\
#                                        x_imag[ix, iy, lz+lzm-nd],nx))
#                            print(phase(y_real[ix, iy, lz+lzm-nd],\
#                                        y_imag[ix, iy, lz+lzm-nd],ny))
#                            print(z_dat[ix, iy, lz+lzm-nd]) 
                            
#                            ndimage.map_coordinates(data[l], traj_pos, mode='wrap', \
#                                          order=interp_order)
                        envsize = 2
                        nx1=lxm-envsize
                        nx2=lxm+envsize+1
                        ny1=lym-envsize
                        ny2=lym+envsize+1
                        nz1=lzm-envsize
                        nz2=lzm+envsize+1
                        
                        dist_data = dist[nx1:nx2,ny1:ny2,nz1:nz2]
                        x0 = np.array([envsize,envsize,envsize],dtype='float')
                        res = minimize(int3d_dist, x0, method='BFGS')
                        #,options={'xtol': 1e-8, 'disp': True})
                        if debug :
                            print('New estimate, relative = {} {} '.\
                                  format(res.x, res.fun))
                        newx = lx-nd+lxm-envsize+res.x[0]
                        newy = ly-nd+lym-envsize+res.x[1]
                        newz = lz-nd+lzm-envsize+res.x[2]
                        if debug :
                            print('New estimate, absolute = {}'.\
                                  format(np.array([newx,newy,newz])))                
                        traj_pos_next_est[kk,:] = np.array([newx,newy,newz])
                    # end kk loop
                #  correction 
            correction_cycle = True

        traj_pos_next_est[:,0][ traj_pos_next_est[:,0] <   0 ] += nx
        traj_pos_next_est[:,0][ traj_pos_next_est[:,0] >= nx ] -= nx
        traj_pos_next_est[:,1][ traj_pos_next_est[:,1] <   0 ] += ny
        traj_pos_next_est[:,1][ traj_pos_next_est[:,1] >= ny ] -= ny
        traj_pos_next_est[:,2][ traj_pos_next_est[:,2] <   0 ]  = 0
        traj_pos_next_est[:,2][ traj_pos_next_est[:,2] >= nz ]  = nz
        
    data_val.append(np.vstack(out[n_pvar:]).T)       
    trajectory.append(traj_pos_next_est) 
    traj_error.append(diff)
    traj_times.append(time)
#    print 'trajectory:',len(trajectory[:-1]), len(trajectory[0]), np.size(trajectory[0][0])
#    print 'traj_error:',len(traj_error[:-1]), len(traj_error[0]), np.size(traj_error[0][0])
    return trajectory, data_val, traj_error, traj_times

def get_sup_obj(sup, t, o) :
    slist = list()
    for s in sup :
        l = (s[:,0] == t)
        st = s[l,:]
        if len(st) >0 :
            st1 = st[st[:,1]==o]
            if len(st1) > 0 : 
#                print(s,st,st1)
                slist.append(s)
    return slist

def whichbox(xvec, x ) :
    """
    Find ix such that xvec[ix]<x<=xvec[ix+1]. Uses numpy.searchsorted.
    
    Args: 
        xvec: Ordered array.
        x: Values to locate in xvec.
    
    Returns:
        Array of indices.
        
    @author : Peter Clark
    """
    
    ix = np.searchsorted(xvec, x, side='left')-1    
    ix[ix > (len(xvec)-1)] = len(xvec)-1
    ix[ix < 0] = 0
    return ix 

def tri_lin_interp(data, pos, xcoord, ycoord, zcoord) :
    """
    Tri-linear interpolation with cyclic wrapround in x and y.
    
    Args: 
        data: list of Input data arrays on 3D grid.
        pos(Array[n,3]): Positions to interpolate to (in grid units) .
        xcoord: 1D coordinate vector.
        ycoord: 1D coordinate vector.
        zcoord: 1D coordinate vector.
    
    Returns:
        list of 1D arrays of data interpolated to pos.
        
    @author : Peter Clark
    """
    
    nx = len(xcoord)
    ny = len(ycoord)
    nz = len(zcoord)

    x = pos[:,0]
    y = pos[:,1]
    z = pos[:,2]
    ix = whichbox(xcoord, x)
    iy = whichbox(ycoord, y)
    iz = whichbox(zcoord, z)
    dx = 1.0
    dy = 1.0
    iz[iz>(nz-2)] -= 1 
    xp = (x-xcoord[ix])/dx
    yp = (y-ycoord[iy])/dy
    zp = (z-zcoord[iz])/(zcoord[iz+1]-zcoord[iz])
    wx = [1.0 - xp, xp]
    wy = [1.0 - yp, yp]
    wz = [1.0 - zp, zp]
    output= list([])
    for l in range(len(data)) :
        output.append(np.zeros_like(x))
    t = 0
    for i in range(0,2):
        for j in range(0,2):
            for k in range(0,2):
                w = wx[i]*wy[j]*wz[k]
                t += w
                for l in range(len(data)) :
                    output[l] = output[l] + data[l][(ix+i)%nx,(iy+j)%ny,iz+k]*w
#                print 'Adding', ix+i,iy+j,iz+k,w,data[ix+i,iy+j,iz+k]
#    print xp, yp, zp
#    print t
    return output

def data_to_pos(data, pos, xcoord, ycoord, zcoord):
    """
    Function to interpolate data to pos.
    
    Args: 
        data      : list of data array.
        pos       : array[n,3] of n 3D positions.
        xcoord,ycoord,zcoord: 1D arrays giving coordinate spaces of data.
                      
    Returns: 
        list of arrays containing interpolated data.   
        
    @author: Peter Clark
    
    """
    
    global interp_order
    if use_bilin :
        output = tri_lin_interp(data, pos, xcoord, ycoord, zcoord )
    else:
        output= list([])
        for l in range(len(data)) :
#            print 'Calling map_coordinates'
#            print np.shape(data[l]), np.shape(traj_pos)
            out = ndimage.map_coordinates(data[l], pos, mode='wrap', \
                                          order=interp_order)
            output.append(out)
    return output

def load_traj_pos_data(dataset, it) :
    """
    Function to read trajectory position variables from file.
    Args: 
        dataset        : netcdf file handle.
        it             : time index in netcdf file.

    Returns:    
        List of arrays containing interpolated data.
        
    @author: Peter Clark
        
    """
    
    if 'CA_xrtraj' in dataset.variables.keys() :
        # Circle-A Version
        trv = {'xr':'CA_xrtraj', \
               'xi':'CA_xitraj', \
               'yr':'CA_yrtraj', \
               'yi':'CA_xitraj', \
               'zpos':'CA_ztraj' } 
        trv_noncyc = {'xpos':'CA_xtraj', \
                      'ypos':'CA_ytraj', \
                      'zpos':'CA_ztraj' } 
    else :
        # Stand-alone Version
        trv = {'xr':'tracer_traj_xr', \
               'xi':'tracer_traj_xi', \
               'yr':'tracer_traj_yr', \
               'yi':'tracer_traj_yi', \
               'zpos':'tracer_traj_zr' } 
        trv_noncyc = {'xpos':'tracer_traj_xr', \
                      'ypos':'tracer_traj_yr', \
                      'zpos':'tracer_traj_zr' } 
        
        
    if cyclic_xy :
        xr = dataset.variables[trv['xr']][it,...]
        xi = dataset.variables[trv['xi']][it,...]

        yr = dataset.variables[trv['yr']][it,...]
        yi = dataset.variables[trv['yi']][it,...]
    
        zpos = dataset.variables[trv['zpos']]
        zposd = zpos[it,...]
        data_list = [xr, xi, yr, yi, zposd]      
        
    else :
        # Non-cyclic option may well not work anymore!
        xpos = dataset.variables[trv_noncyc['xpos']][it,...]
        ypos = dataset.variables[trv_noncyc['ypos']][it,...]
        zpos = dataset.variables[trv_noncyc['zpos']]
        zposd = zpos[it,...]  
        data_list = [xpos, ypos, zposd]

# Needed as zpos above is numpy array not NetCDF variable. 
#    zpos = dataset.variables['CA_ztraj']
    times  = dataset.variables[zpos.dimensions[0]]
             
    return data_list, times[it]  
        
def load_traj_step_data(dataset, it, variable_list, thref) :
    """
    Function to read trajectory variables and additional data from file 
    for interpolation to trajectory.

    Args: 
        dataset        : netcdf file handle.
        it             : time index in netcdf file.
        variable_list  : List of variable names.
        thref          : Array with reference theta profile.

    Returns:    
        List of arrays containing interpolated data.
        
    @author: Peter Clark
        
    """
    
    data_list, time = load_traj_pos_data(dataset, it)
        
    for variable in variable_list :
#        print 'Reading ', variable
        data = dataset.variables[variable]
        data = data[it,...]
        if variable == 'th' :
            data = data+thref[...]
        data_list.append(data)   
        
    return data_list, time  
    
def phase(vr, vi, n) :
    """
    Function to convert real and imaginary points to location on grid 
    size n.
    
    Args: 
        vr,vi  : real and imaginary parts of complex location.
        n      : grid size

    Returns: 
        Real position in [0,n)   
        
    @author: Peter Clark
        
    """
    
    vr = np.asarray(vr)       
    vi = np.asarray(vi)       
    vpos = np.asarray(((np.arctan2(vi,vr))/(2.0*np.pi)) * n )
    vpos[vpos<0] += n
    return vpos    
       
def label_3D_cyclic(mask) :
    """
    Function to label 3D objects taking account of cyclic boundary 
    in x and y. Uses ndimage(label) as primary engine.

    Args:
        mask: 3D logical array with object mask (i.e. objects are 
            contiguous True).  

    Returns:   
        Object identifiers::
        
            labs  : Integer array[nx,ny,nz] of labels. -1 denotes unlabelled.                   
            nobjs : number of distinct objects. Labels range from 0 to nobjs-1.
        
    @author: Peter Clark
         
    """
    
#    print np.shape(mask)        
    (nx, ny, nz) = np.shape(mask)
    labels, nobjects = ndimage.label(mask)
    labels -=1
#    print 'labels', np.shape(labels)     
    def relabel(labs, nobjs, i,j) :
#        if debug_label : 
#            print('Setting label {:3d} to {:3d}'.format(j,i)) 
        lj = (labs == j)
        labs[lj] = i
        for k in range(j+1,nobjs) :
            lk = (labs == k)
            labs[lk] = k-1
#            if debug_label : 
#                print('Setting label {:3d} to {:3d}'.format(k,k-1)) 
        nobjs -= 1
#        if debug_label : print('nobjects = {:d}'.format(nobjects))
        return labs, nobjs
    
    def find_objects_at_edge(minflag, x_or_y, n, labs, nobjs) :
#        for minflag in (True,False) :
        i = 0
        while i < (nobjs-2) :
            posi = np.where(labs == i)
#        print(np.shape(posi))
            if minflag :
                test1 = (np.min(posi[x_or_y][:]) == 0)
                border = '0'
            else:
                test1 = (np.max(posi[x_or_y][:]) == (n-1))
                border = 'n{}-1'.format(['x','y'][x_or_y])
            if test1 :
                if debug_label : 
                    print('Object {:03d} on {}={} border?'.\
                          format(i,['x','y'][x_or_y],border))
                j = i+1
                while j < (nobjs-1) :
                    posj = np.where(labs == j)
                    
                    if minflag :
                        test2 = (np.max(posj[x_or_y][:]) == (n-1))
                        border = 'n{}-1'.format(['x','y'][x_or_y])
                    else:
                        test2 = (np.min(posj[x_or_y][:]) == 0)
                        border = '0'
                        
                    if test2 :
                        if debug_label : 
                            print('Match Object {:03d} on {}={} border?'\
                                  .format(j,['x','y'][x_or_y],border))
                            
                        if minflag :
                            ilist = np.where(posi[x_or_y][:] == 0)
                            jlist = np.where(posj[x_or_y][:] == (n-1))
                        else :
                            ilist = np.where(posi[x_or_y][:] == (n-1))
                            jlist = np.where(posj[x_or_y][:] == 0)
                            
                        if np.size( np.intersect1d(posi[1-x_or_y][ilist], \
                                           posj[1-x_or_y][jlist]) ) :
                            if np.size( np.intersect1d(posi[2][ilist], \
                                           posj[2][jlist]) ) :
                            
                                if debug_label : 
                                    print('Yes!',i,j)
#                                    for ii in range(3) : 
#                                        print(ii, posi[ii][posi[x_or_y][:] \
#                                                       == 0])
#                                    for ii in range(3) : 
#                                        print(ii, posj[ii][posj[x_or_y][:] \
#                                                       == (n-1)])
                                labs, nobjs = relabel(labs, nobjs, i, j)
                    j += 1
            i += 1
        return labs, nobjs

    labels, nobjects = find_objects_at_edge(True,  0, nx, labels, nobjects)
    labels, nobjects = find_objects_at_edge(False, 0, nx, labels, nobjects)
    labels, nobjects = find_objects_at_edge(True,  1, ny, labels, nobjects)
    labels, nobjects = find_objects_at_edge(False, 1, ny, labels, nobjects)
       
    return labels, nobjects

def unsplit_object( pos, nx, ny ) :
    """
    Function to gather together points in object separated by cyclic boundaries. 
        For example, if an object spans the 0/nx boundary, so some 
        points are close to zero, some close to nx, they will be adjusted to 
        either go from negative to positive, close to 0, or less than nx to 
        greater than. The algorithm tries to group on the larges initial set.
        Uses sklearn.cluster.KMeans as main engine.
    
    Args: 
        pos      : grid positions of points in object.
        nx,ny    : number of grid points in x and y directions.
    Returns:    
        Adjusted grid positions of points in object.
  
    @author: Peter Clark
        
    """
    
    global debug_unsplit
    if debug_unsplit : print('pos:', pos)
    n_clust = np.min([4,np.shape(pos)[0]])
    if debug_unsplit : print('Shape(pos):',np.shape(pos), \
                             'Number of clutsters:', n_clust)
    kmeans = KMeans(n_clusters=n_clust)
#    print(kmeans)
    kmeans.fit(pos)
#    print(kmeans)
    
    if debug_unsplit : print('Shape(cluster centres):', \
                            np.shape(kmeans.cluster_centers_))
    if debug_unsplit : print('Cluster centres: ',kmeans.cluster_centers_)
    counts = np.zeros(n_clust,dtype=int)
    for i in range(n_clust):
        counts[i] = np.count_nonzero(kmeans.labels_ == i)
    if debug_unsplit : print(counts)
    main_cluster = np.where(counts == np.max(counts))[0]
    def debug_print(j) :
        print('Main cluster:', main_cluster, 'cluster number: ', i, \
              'dist:', dist)
        print('Cluster centres:', kmeans.cluster_centers_)           
        print('Changing ', pos[kmeans.labels_ == i,j])
        return
    
    for i in range(n_clust):     
        dist = kmeans.cluster_centers_[i] - kmeans.cluster_centers_[main_cluster]
#        print 'dist', dist
        dist = dist[0]
        if (dist[0] < -nx/2) :
            if debug_unsplit : debug_print(0)
            pos[kmeans.labels_ == i,0] = pos[kmeans.labels_ == i,0] + nx
        if (dist[0] >  nx/2) :
            if debug_unsplit : debug_print(0)
            pos[kmeans.labels_ == i,0] = pos[kmeans.labels_ == i,0] - nx
        if (dist[1] < -ny/2) :
            if debug_unsplit : debug_print(1)
            pos[kmeans.labels_ == i,1] = pos[kmeans.labels_ == i,1] + ny
        if (dist[1] >  ny/2) :
            if debug_unsplit : debug_print(1)
            pos[kmeans.labels_ == i,1] = pos[kmeans.labels_ == i,1] - ny
    
    return pos
    
def unsplit_objects(trajectory, labels, nobjects, nx, ny) :
    """
    Function to unsplit a set of objects at a set of times using 
    unsplit_object on each.
    
    Args: 
        trajectory     : Array[nt, np, 3] of trajectory points, with nt \
                         times and np points.
        labels         : labels of trajectory points.
        nx,ny   : number of grid points in x and y directions.
    Returns:    
        Trajectory array with modified positions.
  
    @author: Peter Clark
        
    """
    
    global debug_unsplit
#    print np.shape(trajectory)
    print('Unsplitting Objects:')

    for iobj in range(0,nobjects):
        if debug_unsplit : print('Unsplitting Object: {:03d}'.format(iobj))
#        if iobj == 15 : 
#            debug_unsplit = True
#        else :
#            debug_unsplit = False

        for it in range(0,np.shape(trajectory)[0]) :
            if debug_unsplit : print('Time: {:03d}'.format(it))
            tr = trajectory[it,labels == (iobj),:]
            if ((np.max(tr[:,0])-np.min(tr[:,0])) > nx/2 ) or \
               ((np.max(tr[:,1])-np.min(tr[:,1])) > ny/2 ) :
                trajectory[it, labels == iobj,:] = \
                unsplit_object(trajectory[it,labels == iobj,:], \
                                               nx, ny)
                if debug_unsplit : print('New object:',\
                    trajectory[it,labels == iobj,:])
    return trajectory
    
def compute_traj_boxes(traj, in_obj_func, kwargs={}) :
    """
    Function to compute two rectangular boxes containing all and in_obj 
    points for each trajectory object and time, plus some associated data.
    
    Args: 
        traj               : trajectory object.
        in_obj_func        : function to determine which points are inside an object.
        kwargs             : any additional keyword arguments to ref_func (dict).

    Returns:  
        Properties of in_obj boxes::
        
            data_mean        : mean of points (for each data variable) in in_obj. 
            in_obj_data_mean : mean of points (for each data variable) in in_obj. 
            num_in_obj       : number of in_obj points.
            traj_centroid    : centroid of in_obj box.
            in_obj__centroid : centroid of in_obj box.
            traj_box         : box coordinates of each trajectory set.
            in_obj_box       : box coordinates for in_obj points in each trajectory set.                           
  
    @author: Peter Clark
        
    """
    
    scalar_shape = (np.shape(traj.data)[0], traj.nobjects)
    centroid_shape = (np.shape(traj.data)[0], traj.nobjects, \
                      3)
    mean_obj_shape = (np.shape(traj.data)[0], traj.nobjects, \
                      np.shape(traj.data)[2])
    box_shape = (np.shape(traj.data)[0], traj.nobjects, 2, 3)
    
    data_mean = np.zeros(mean_obj_shape)
    in_obj_data_mean = np.zeros(mean_obj_shape)
    objvar_mean = np.zeros(scalar_shape)
    num_in_obj = np.zeros(scalar_shape, dtype=int)
    traj_centroid = np.zeros(centroid_shape)
    in_obj_centroid = np.zeros(centroid_shape)
    traj_box = np.zeros(box_shape)
    in_obj_box = np.zeros(box_shape)
    
    in_obj_mask, objvar = in_obj_func(traj, **kwargs)
    
    for iobj in range(traj.nobjects):
        
        data = traj.data[:,traj.labels == iobj,:]
        data_mean[:,iobj,:] = np.mean(data, axis=1) 
        obj = traj.trajectory[:, traj.labels == iobj, :]

        traj_centroid[:,iobj, :] = np.mean(obj,axis=1) 
        traj_box[:,iobj, 0, :] = np.amin(obj, axis=1)
        traj_box[:,iobj, 1, :] = np.amax(obj, axis=1)
        
        objdat = objvar[:,traj.labels == iobj]
        
        for it in np.arange(0,np.shape(obj)[0]) : 
            mask = in_obj_mask[it, traj.labels == iobj]
            num_in_obj[it, iobj] = np.size(np.where(mask))
            if num_in_obj[it, iobj] > 0 :
                in_obj_data_mean[it, iobj, :] = np.mean(data[it, mask, :], axis=0) 
                objvar_mean[it, iobj] = np.mean(objdat[it, mask])
                in_obj_centroid[it, iobj, :] = np.mean(obj[it, mask, :],axis=0)                
                in_obj_box[it, iobj, 0, :] = np.amin(obj[it, mask, :], axis=0)
                in_obj_box[it, iobj, 1, :] = np.amax(obj[it, mask, :], axis=0)
    return data_mean, in_obj_data_mean, objvar_mean, num_in_obj, \
           traj_centroid, in_obj_centroid, traj_box, in_obj_box
   
    
def print_boxes(traj) : 
    """
        Function to print information provided by compute_traj_boxes stored 
        as attributes of traj.
        
        Args: 
            traj : trajectory object.
            
        @author: Peter Clark
        
    """
    
    varns = list(traj.variable_list)
    for iobj in range(traj.nobjects) :
        print('Object {:03d}'.format(iobj))
        print('  Time    x      y      z   '+\
              ''.join([' {:^10s}'.format(varns[i][:9]) for i in range(6)]))
        for it in range(np.shape(traj.centroid)[0]) :
            strf = '{:6.0f}'.format(traj.times[it]/60)
            strf = strf + ''.join([' {:6.2f}'.\
                    format(traj.centroid[it,iobj,i]) for i in range(3)]) 
            strf = strf + ''.join([' {:10.6f}'.\
                    format(traj.data_mean[it,iobj,i]) for i in range(6)])
            print(strf)
    return 

def box_overlap_with_wrap(b_test, b_set, nx, ny) :
    """
        Function to compute whether rectangular boxes intersect.
        
        Args: 
            b_test: box for testing array[8,3]
            b_set: set of boxes array[n,8,3]
            nx: number of points in x grid.
            ny: number of points in y grid.
           
        Returns:
            indices of overlapping boxes
            
        @author: Peter Clark
        
    """
    
    # Wrap not yet implemented
    
    t1 = np.logical_and( \
        b_test[0,0] >= b_set[...,0,0] , b_test[0,0] <= b_set[...,1,0])
    t2 = np.logical_and( \
        b_test[1,0] >= b_set[...,0,0] , b_test[1,0] <= b_set[...,1,0])
    t3 = np.logical_and( \
        b_test[0,0] <= b_set[...,0,0] , b_test[1,0] >= b_set[...,1,0])
    t4 = np.logical_and( \
        b_test[0,0] >= b_set[...,0,0] , b_test[1,0] <= b_set[...,1,0])
    x_overlap =np.logical_or(np.logical_or( t1, t2), np.logical_or( t3, t4) )

#    print(x_overlap)
    x_ind = np.where(x_overlap)[0]
#    print(x_ind)
    t1 = np.logical_and( \
        b_test[0,1] >= b_set[x_ind,0,1] , b_test[0,1] <= b_set[x_ind,1,1])
    t2 = np.logical_and( \
        b_test[1,1] >= b_set[x_ind,0,1] , b_test[1,1] <= b_set[x_ind,1,1])
    t3 = np.logical_and( \
        b_test[0,1] <= b_set[x_ind,0,1] , b_test[1,1] >= b_set[x_ind,1,1])
    t4 = np.logical_and( \
        b_test[0,1] >= b_set[x_ind,0,1] , b_test[1,1] <= b_set[x_ind,1,1])
    y_overlap = np.logical_or(np.logical_or( t1, t2), np.logical_or( t3, t4) )
    
    y_ind = np.where(y_overlap)[0]
    
    return x_ind[y_ind]

def file_key(file):
    f1 = file.split('_')[-1]
    f2 = f1.split('.')[0]
    return float(f2)

def find_time_in_files(files, ref_time, nodt = False) :
    r"""
    Function to find file containing data at required time.
        Assumes file names are of form \*_tt.0\* where tt is model output time.

    Args: 
        files: ordered list of files
        ref_time: required time.
        nodt: if True do not look for next time to get delta_t

    Returns:
        Variables defining location of data in file list::
        
            ref_file: Index of file containing required time in files.
            it: Index of time in dataset. 
            delta_t: Interval between data.

    @author: Peter Clark
    
    """
    
    file_times = np.zeros(len(files))
    for i, file in enumerate(files) : file_times[i] = file_key(file)
    
    def get_file_times(dataset) :
        theta=dataset.variables["th"]
#        print(theta)
#        print(theta.dimensions[0])
        t=dataset.variables[theta.dimensions[0]][...]
#        print(t)
        return t
    
    delta_t = 0.0
    it=-1
    ref_file = np.where(file_times >= ref_time)[0][0]
    while True :
        if ref_file >= len(files) or ref_file < 0 :
            ref_file = None
            break
#        print(files[ref_file])
        dataset=Dataset(files[ref_file])
        times = get_file_times(dataset)
        dataset.close()
#        print(times)
    
        if len(times) == 1 :
            dataset.close()
            it = 0
            if times[it] != ref_time :
                print('Could not find exact time {} in file {}'.\
                  format(ref_time,files[ref_file]))
                ref_file = None
            else :
                if nodt :
                    delta_t = 0.0
                else :
                    print('Looking in next file to get dt.')
                    dataset_next=Dataset(files[ref_file+1])
                    times_next = get_file_times(dataset_next)
                    delta_t = times_next[0] - times[0]
                    dataset_next.close()
            break 
                
        else : # len(times) > 1
            it = np.where(times == ref_time)[0]
            if len(it) == 0 :
                print('Could not find exact time {} in file {}'.\
                  format(ref_time,ref_file))
                it = np.where(times >= ref_time)[0]
#                print("it={}".format(it))
                if len(it) == 0 :
                    print('Could not find time >= {} in file {}, looking in next.'.\
                      format(ref_time,ref_file))
                    ref_file += 1
                    continue
#            else :
            it = it[0]
            if it == (len(times)-1) :
                delta_t = times[it] - times[it-1]
            else :
                delta_t = times[it+1] - times[it]
            break
    print(\
    "Looking for time {}, returning file #{}, index {}, time {}, delta_t {}".\
          format(  ref_time,ref_file, it, times[it], delta_t) )
    return ref_file, it, delta_t.astype(int)

def compute_derived_variables(traj, derived_variable_list=None) :
    if derived_variable_list is None :
        derived_variable_list = { \
                           "q_total":r"$q_{t}$ kg/kg", \
                           "th_L":r"$\theta_L$ K", \
                           "th_v":r"$\theta_v$ K", \
                           "MSE":r"MSE J kg$^{-1}$", \
                           }
    data_list = list([])        
    tr_z = (traj.trajectory[...,2]-0.5)*traj.deltaz
    zn = (np.arange(0,np.size(traj.piref))-0.5)*traj.deltaz
    piref_z = np.interp(tr_z,zn,traj.piref)
    thref_z = np.interp(tr_z,zn,traj.thref)
    
    s = list(np.shape(traj.data))
#    print(s)
    s.pop()
    s.append(len(derived_variable_list))
#    print(s)
    out = np.zeros(s)
#    print(np.shape(out))
    
    for i,variable in enumerate(derived_variable_list.keys()) :
        
        if variable == "q_total" :
            data = traj.data[..., traj.var("q_vapour")] + \
                   traj.data[..., traj.var("q_cloud_liquid_mass")]
                 
        if variable == "th_L" :
            data = traj.data[..., traj.var("th")] - \
              L_over_cp * \
              traj.data[..., traj.var("q_cloud_liquid_mass")] \
              / piref_z
              
        if variable == "th_v" :
            data = traj.data[..., traj.var("th")] + \
                   thref_z * (c_virtual * \
                              traj.data[..., traj.var("q_vapour")] - 
                              traj.data[..., traj.var("q_cloud_liquid_mass")])

        if variable == "MSE" :
            data = traj.data[:, :, traj.var("th")] * \
                          Cp * piref_z + \
                          grav * tr_z + \
                          L_vap * traj.data[:, :, traj.var("q_vapour")]
                          
#        print(variable, np.min(data),np.max(data),np.shape(data))
            
        out[...,i] = data
#        data_list.append(data)   
#    out = np.vstack(data_list).T
#    out = np.array(data_list).T
#    print(np.shape(out))
    return derived_variable_list, out

def set_cloud_class(traj, thresh=None, version=1) :
    '''
    Function to compute trajectory class and mean cloud properties.

    Args:
        thresh: Threshold if LWC to define cloud. Default is traj.thresh.
        version: Which version of classification. (Currently only 1).

    Returns: 
        Dictionary containing trajectory class points, key and useful derived data::
        
          Dictionary keys:
          "class"
          "key"
          "first_cloud_base"
          "min_cloud_base"
          "cloud_top"
          "cloud_trigger_time"
          "cloud_dissipate_time"
          "version":version
        
    @author: Peter Clark

    '''
    if version == 1 :
        PRE_CLOUD_ENTR_FROM_BL = 1
        PRE_CLOUD_ENTR_FROM_ABOVE_BL = 2
        PREVIOUS_CLOUD = 3
        DETR_PREV = 4
        POST_DETR_PREV = 5
        CLOUD = 6
        ENTR_FROM_BL = 7
        ENTR_FROM_ABOVE_BL = 8
#            ENTR_PREV_CLOUD = 7
        DETRAINED = 9
        POST_DETR = 10
        SUBSEQUENT_CLOUD = 11
    else :
        print("Illegal Version")
        return 

    class_key = list([\
        "Not set" , \
        "PRE_CLOUD_ENTR_FROM_BL", \
        "PRE_CLOUD_ENTR_FROM_ABOVE_BL", \
        "PREVIOUS_CLOUD", \
        "DETR_PREV", \
        "POST_DETR_PREV", \
        "CLOUD", \
        "ENTRAINED_FROM_BL", \
        "ENTRAINED_FROM_ABOVE_BL", \
        "DETRAINED", \
        "POST_DETR", \
        "SUBS_CLOUD", \
        ])

    if thresh == None : thresh = traj.ref_func_kwargs["thresh"]
    traj_class = np.zeros_like(traj.data[:,:,0], dtype=int)
    
    min_cloud_base = np.zeros(traj.nobjects)
    first_cloud_base = np.zeros(traj.nobjects)
    cloud_top = np.zeros(traj.nobjects)
    cloud_trigger_time = np.zeros(traj.nobjects, dtype=int)
    cloud_dissipate_time = np.ones(traj.nobjects, dtype=int)*traj.ntimes

    tr_z = (traj.trajectory[:,:,2]-0.5)*traj.deltaz
    zn = (np.arange(0,np.size(traj.piref))-0.5)*traj.deltaz
    
    for iobj in range(0,traj.nobjects) :
#        debug_mean = (iobj == 61)
        if debug_mean : print('Processing object {}'.format(iobj))
        obj_ptrs = (traj.labels == iobj)
        where_obj_ptrs = np.where(obj_ptrs)[0]
        tr = traj.trajectory[:, obj_ptrs, :]
        data = traj.data[:, obj_ptrs, :]
        obj_z = tr_z[:,obj_ptrs]
        
        if debug_mean : print(np.shape(data))
        
        qcl = data[:,:,traj.var("q_cloud_liquid_mass")]
        mask_qcl = (qcl >= thresh)
        w = data[:,:,traj.var("w")]
        mask_w = (w >= 0.1)
#        mask = np.logical_and(mask_qcl, mask_w)
        mask = mask_qcl       
#        print("Object ",iobj, np.size(np.where(mask[traj.ref,:])[0]))
        
        if np.size(np.where(mask[traj.ref,:])[0]) == 0 :
            print("Object {} is not active at reference time.".format(iobj))
            continue
 
        # Original extracted variables
        min_cloud_base[iobj] = (np.min(tr[mask,2])-0.5)*traj.deltaz
#        data_class = traj_class[:,traj.labels == iobj]
        if debug_mean : print('Version ',version)

#        if version == 1 :
            
        in_main_cloud = True
        
        for it in range(traj.ref,-1,-1) :
            
            if debug_mean : print("it = {}".format(it))

            cloud_bottom = traj.in_obj_box[it, iobj, 0, 2]
            
            cloud = mask[it,:]
            where_cloud = np.where(cloud)[0]
            
            not_cloud = np.logical_not(cloud)
            where_not_cloud = np.where(not_cloud)[0]

            if it > 0 :
                
                cloud_at_prev_step = mask[it-1,:]
                not_cloud_at_prev_step = np.logical_not(\
                                            cloud_at_prev_step) 
                
                new_cloud = np.logical_and(cloud, \
                                           not_cloud_at_prev_step)
                where_newcloud = np.where(new_cloud)[0]
                
                not_new_cloud = np.logical_and(cloud, \
                                               cloud_at_prev_step)
                where_not_newcloud = np.where(not_new_cloud)[0]
#                            print(np.size(where_newcloud),np.size(where_not_newcloud))
            else :
                where_newcloud = np.array([])

                not_new_cloud = cloud
                where_not_newcloud = where_cloud
                        
            if np.size(where_cloud) > 0 :  
                # There are cloudy points                            
                # Find new cloudy points  
                    
                if np.size(where_newcloud) > 0 : # Entrainment
                    if debug_mean : print('Entraining air')

                    # New cloud in air that starts below cloud base.
                    newcl_from_bl = np.logical_and( new_cloud,\
                                      obj_z[0, :] < min_cloud_base[iobj])  
                    where_newcl_from_bl = np.where(newcl_from_bl)[0]
                    class_set_from_bl = where_obj_ptrs[ \
                                      where_newcl_from_bl]
                    
                    # New cloud in air that starts above cloud base.
                    newcl_from_above_bl = np.logical_and( new_cloud,\
                                     obj_z[0, :] >= min_cloud_base[iobj])  
                    where_newcl_from_above_bl = np.where( \
                                                newcl_from_above_bl)[0]
                    class_set_from_above_bl = where_obj_ptrs[ \
                                            where_newcl_from_above_bl]
                    
                    traj_class[0:it, class_set_from_bl] = \
                                PRE_CLOUD_ENTR_FROM_BL 
                    traj_class[it, class_set_from_bl] = \
                                ENTR_FROM_BL 
                                
                    traj_class[0:it, class_set_from_above_bl] = \
                                PRE_CLOUD_ENTR_FROM_ABOVE_BL
                    traj_class[it, class_set_from_above_bl] = \
                                ENTR_FROM_ABOVE_BL

                    if debug_mean : 
                        print("From BL",class_set_from_bl)
                        print("From above BL",class_set_from_above_bl)
#                        input("Press Enter to continue...")
                    
                # Set traj_class flag for those points in cloud.              
                if np.size(where_not_newcloud) > 0 : # Not entrainment
                    if debug_mean : 
                        print("Setting Cloud",it,\
                              np.size(where_not_newcloud))
                        
                    class_set = where_obj_ptrs[where_not_newcloud]
                
                    if in_main_cloud :
                        # Still in cloud contiguous with reference time.
                        traj_class[it, class_set] = CLOUD
                        if debug_mean : 
                            print("CLOUD",class_set)
                    else :
                        # Must be cloud points that were present before.
                        traj_class[it, class_set] = PREVIOUS_CLOUD
                        if debug_mean : 
                            print("PREV CLOUD",class_set)
                        
            else : # np.size(where_cloud) == 0 
                if in_main_cloud : cloud_trigger_time[iobj] = it+1
                in_main_cloud = False
                
            # Now what about detraining air?
            if np.size(where_not_cloud) > 0 : 
                
#                    if it == traj.ref :
#                        print("Problem - reference not all cloud",iobj)
                
                                        
                # Find points that have ceased to be cloudy     
                if it > 0 :
                    detr_cloud = np.logical_and(not_cloud, \
                                                cloud_at_prev_step)
                    where_detrained = np.where(detr_cloud)[0]
                                                
                    if np.size(where_detrained) > 0 : # Detrainment
                        if debug_mean : print('Detraining air')
                            
                        class_set = where_obj_ptrs[where_detrained] 
                        if in_main_cloud :
                            traj_class[it, class_set] = DETRAINED
                            if debug_mean : 
                                print("Detrained",class_set)
                            for iit in range(it+1,traj.ref) :
                                post_detr = np.logical_and(detr_cloud, \
                                                   np.logical_not(mask[iit,:]))
                                where_post_detr = np.where(post_detr)[0]
                                class_set_post_detr = where_obj_ptrs[ \
                                                where_post_detr]
                                traj_class[iit, class_set_post_detr] = \
                                    POST_DETR                             
                                if debug_mean : 
                                    print("Post detr",iit, class_set_post_detr)
                        else :
                            traj_class[it, class_set] = DETR_PREV
                            if debug_mean : 
                                print("Detrained prev",class_set)
                            for iit in range(it+1,traj.ref) :
                                post_detr_prev = np.logical_and(detr_cloud, \
                                                   np.logical_not(mask[iit,:]))
                                where_post_detr_prev = np.where(post_detr_prev)[0]
                                class_set_post_detr_prev = where_obj_ptrs[ \
                                                where_post_detr_prev]
                                traj_class[iit, class_set_post_detr_prev] = \
                                    POST_DETR_PREV                             
                                if debug_mean : 
                                    print("Post detr prev",iit, class_set_post_detr_prev)
                        if debug_mean : 
                            input("Press Enter to continue...")     
                            
        in_main_cloud = True
        after_cloud_dissipated = False  

        for it in range(traj.ref+1,traj.end+1) :
            
            if debug_mean : print("it = {}".format(it))
            
            cloud_bottom = traj.in_obj_box[it, iobj, 0, 2]
            
            cloud = mask[it,:]
            where_cloud = np.where(cloud)[0]
            
            not_cloud = np.logical_not(cloud)
            where_not_cloud = np.where(not_cloud)[0]
            
            cloud_at_prev_step = mask[it-1,:]
            not_cloud_at_prev_step = np.logical_not(\
                                        cloud_at_prev_step) 
            
            new_cloud = np.logical_and(cloud, \
                                       not_cloud_at_prev_step)
            where_newcloud = np.where(new_cloud)[0]
            
            not_new_cloud = np.logical_and(cloud, \
                                           cloud_at_prev_step)
            where_not_newcloud = np.where(not_new_cloud)[0]
            
            new_not_cloud = np.logical_and(not_cloud, \
                                       cloud_at_prev_step)
            where_new_not_cloud = np.where(new_not_cloud)[0]
            
            not_new_not_cloud = np.logical_and(not_cloud, \
                                       not_cloud_at_prev_step)
            where_not_new_not_cloud = np.where(not_new_not_cloud)[0]

            
#            if debug_mean : 
#                print('it', it, np.shape(where_cloud))
#                print(qcl[it,mask[it,:]])
#                print(new_cloud)
#                print(qcl[it-1,new_cloud],qcl[it,new_cloud])
            
                # Find new cloudy points  

            if np.size(where_newcloud) > 0 : # Entrainment
                if debug_mean : print('Entraining air')
                
                class_set = where_obj_ptrs[where_newcloud]
                           
                traj_class[it-1, class_set] = \
                            PRE_CLOUD_ENTR_FROM_ABOVE_BL
                traj_class[it, class_set] = \
                            ENTR_FROM_ABOVE_BL

                if debug_mean : 
#                                print("From BL",class_set_from_bl)
                    print("From above BL",class_set)
 
                
            # Set traj_class flag for those points in cloud.              
            if np.size(where_not_newcloud) > 0 : # Existing cloud
                
                if debug_mean : print("Setting Cloud",it,np.size(where_not_newcloud))
                
                class_set = where_obj_ptrs[where_not_newcloud]
            
                if in_main_cloud :
                    # Still in cloud contiguous with reference time.
                    traj_class[it, class_set] = CLOUD
                    if debug_mean : 
                        print("Cloud",class_set)
                else :
                    # Must be cloud points that were present before.
                    traj_class[it, class_set] = SUBSEQUENT_CLOUD                           
                    if debug_mean : 
                        print("Subs Cloud",class_set)

#                          (np.max(tr[it-1,cloud_at_prev_step,2])-0.5) * traj.deltaz

                
            # Now what about detraining and detraining air?
            if np.size(where_new_not_cloud) > 0 : 
                class_set = where_obj_ptrs[where_new_not_cloud]
                traj_class[it, class_set] = DETRAINED
                if debug_mean : 
                    print("DETRAINED",class_set)

            if np.size(where_not_new_not_cloud) > 0 : 
                class_set = where_obj_ptrs[where_not_new_not_cloud]
                traj_class[it, class_set] = POST_DETR
                if debug_mean : 
                    print("POST DETRAINED",class_set)
                
            if np.size(where_cloud) == 0 :  
                # There are cloudy points
                if in_main_cloud and not after_cloud_dissipated :
                    # At cloud top.
                    cloud_dissipate_time[iobj] = it
                    cloud_top[iobj] = np.max(obj_z[it-1,cloud_at_prev_step])
                    in_main_cloud = False
                    after_cloud_dissipated = True  
                if debug_mean : 
                    input("Press Enter to continue...") 


    traj_class = { \
                   "class":traj_class, \
                   "key":class_key, \
                   "first_cloud_base":first_cloud_base, \
                   "min_cloud_base":min_cloud_base, \
                   "cloud_top":cloud_top, \
                   "cloud_trigger_time":cloud_trigger_time, \
                   "cloud_dissipate_time":cloud_dissipate_time, \
                   "version":version, \
                 }
    return traj_class

def print_cloud_class(traj, traj_cl, sel_obj, list_classes=True) :
    '''
    Function to compute trajectory class and mean cloud properties.

    Args:
        traj       : Trajectory object
        traj_cl    : Dict of Classifications of trajectory points 
            provided by set_cloud_class function.
        
    @author: Peter Clark

    '''

    tr_class = traj_cl["class"][:,traj.labels == sel_obj]
    if list_classes :
        for (iclass,key) in enumerate(traj_cl["key"]) :
            print("{:2d}: {}".format(iclass,key))
    
    strout = "time "
    for (iclass,key) in enumerate(traj_cl["key"]) :
        strout += "{:5d} ".format(iclass)
    strout += " total"
    print(strout)
    
    for it in range(0, traj.end+1) :
        strout = "{:4d} ".format(it) 
        tot = 0
        for (iclass, key) in enumerate(traj_cl["key"]) :
            in_cl = (tr_class[it,:] == iclass)
            num_in_class = np.size(np.where(in_cl)[0])
            strout += "{:5d} ".format(num_in_class)
            tot += num_in_class
        strout += "{:6d} ".format(tot)
        print(strout)
       
def cloud_properties(traj, traj_cl, thresh=None, use_density = False) :
    '''
    Function to compute trajectory class and mean cloud properties.

    Args:
        traj       : Trajectory object
        traj_cl    : Dict of Classifications of trajectory points 
            provided by set_cloud_class function.
        thresh     : Threshold if LWC to define cloud. Default is traj.thresh.

    Returns: 
        dictionary pointing to arrays of mean properties and meta data::
        
            Dictionary keys:
                "overall_mean"
                "unclassified"
                "pre_cloud_bl"
                "pre_cloud_above_bl"
                "previous_cloud"
                "detr_prev"
                "post_detr_prev"
                "cloud"
                "entr_bot"
                "entr"
                "detr"
                "post_detr"
                "subsequent_cloud"
                "cloud_properties"
                "budget_loss"
                "entrainment"
                "derived_variable_list"
        
    @author: Peter Clark

    '''
 
    if thresh == None : thresh = traj.ref_func_kwargs["thresh"]
    version = traj_cl["version"]
    if version == 1 :
        n_class = len(traj_cl["key"])
        UNCLASSIFIED = traj_cl["key"].index('Not set')
        PRE_CLOUD_ENTR_FROM_BL = traj_cl["key"].index('PRE_CLOUD_ENTR_FROM_BL')
        PRE_CLOUD_ENTR_FROM_ABOVE_BL = traj_cl["key"].index('PRE_CLOUD_ENTR_FROM_ABOVE_BL')
        PREVIOUS_CLOUD = traj_cl["key"].index('PREVIOUS_CLOUD')
        DETR_PREV = traj_cl["key"].index('DETR_PREV')
        POST_DETR_PREV = traj_cl["key"].index('POST_DETR_PREV')
        CLOUD = traj_cl["key"].index('CLOUD')
        ENTR_FROM_BL = traj_cl["key"].index('ENTRAINED_FROM_BL')
        ENTR_FROM_ABOVE_BL = traj_cl["key"].index('ENTRAINED_FROM_ABOVE_BL')
        DETRAINED = traj_cl["key"].index('DETRAINED')
        POST_DETR = traj_cl["key"].index('POST_DETR')
        SUBSEQUENT_CLOUD = traj_cl["key"].index('SUBS_CLOUD')
    else :
        print("Illegal Version")
        return 
    
    traj_class = traj_cl["class"]
    
    derived_variable_list, derived_data = compute_derived_variables(traj)
                    
    nvars = np.shape(traj.data)[2]
    ndvars = np.shape(derived_data)[2]
    nposvars = 3
    total_nvars = nvars + ndvars + nposvars + 1

    z_ptr = nvars + ndvars + 2 # Index of variable in mean_prop which is height
    npts_ptr = nvars + ndvars + nposvars # Index of variable in mean_prop which is 
    w_ptr = traj.var('w')
    mse_ptr = nvars + list(derived_variable_list.keys()).index("MSE") 
    qt_ptr = nvars + list(derived_variable_list.keys()).index("q_total")

    grid_box_area = traj.deltax * traj.deltay
    grid_box_volume = grid_box_area * traj.deltaz
    
    rho = np.interp(traj.trajectory[:,:,2],traj.zcoord,traj.rhoref)
    
#    print(nvars, ndvars, nposvars)
    # These possible slices are set for ease of maintenance.
    # Main data variables.
    r1 = slice(0,nvars)
    # Derived variables
    r2 = slice(nvars, nvars+ndvars)
    # Position
    r3 = slice(nvars+ndvars,nvars+ndvars+nposvars)
    # Number of points
    r4 = nvars + ndvars + nposvars 
    
    if version == 1 :
        mean_prop = np.zeros([traj.ntimes, traj.nobjects, total_nvars])
        
        mean_prop_by_class = np.zeros([traj.ntimes, traj.nobjects, \
                                       total_nvars,  n_class+1])
        budget_loss = np.zeros([traj.ntimes-1, traj.nobjects, total_nvars-1])
        
        # Pointers into cloud_prop array
        CLOUD_HEIGHT = 0
        CLOUD_POINTS = 1
        CLOUD_VOLUME = 2
        n_cloud_prop = 3
        
        cloud_prop = np.zeros([traj.ntimes, traj.nobjects, n_cloud_prop])
        
        # Pointers into entrainment array                            
        TOT_ENTR = 0
        TOT_ENTR_Z = 1
        SIDE_ENTR = 2
        SIDE_ENTR_Z = 3
        CB_ENTR = 4
        CB_ENTR_Z = 5
        DETR = 6
        DETR_Z = 7
        n_entr_vars = 8
        entrainment = -np.ones([traj.ntimes-1, traj.nobjects, n_entr_vars])
        
        max_cloud_base_area = np.zeros(traj.nobjects)
        max_cloud_base_time = np.zeros(traj.nobjects, dtype = int)
        cloud_base_variables = np.zeros([traj.nobjects, total_nvars-1])
       
    else :
        print("Illegal Version")
        return 
                                  
# Compute mean properties of cloudy points. 
   
    for iobj in range(0,traj.nobjects) :
#        debug_mean = (iobj == 61)
        if debug_mean : print('Processing object {}'.format(iobj))
        
        obj_ptrs = (traj.labels == iobj)
        
#        where_obj_ptrs = np.where(obj_ptrs)[0]
        tr = traj.trajectory[:, obj_ptrs, :]
        data = traj.data[:, obj_ptrs, :]
        derv_data = derived_data[:, obj_ptrs, :]
#        obj_z = tr_z[:,obj_ptrs]
        
#        if debug_mean : print(np.shape(data), np.shape(derv_data))
        
#        qcl = data[:,:,traj.var("q_cloud_liquid_mass")]
#        mask_qcl = (qcl >= thresh)
#        w = data[:,:,traj.var("w")]
#        mask_w = (w >= 0.1)
#        mask = np.logical_and(mask_qcl, mask_w)
#        
##        print("Object ",iobj, np.size(np.where(mask[traj.ref,:])[0]))
#        
#        if np.size(np.where(mask[traj.ref,:])[0]) == 0 :
#            print("Object {} is not active at reference time.".format(iobj))
#            continue

# Sum properties over classes; division by number of points happens later.
        for it in range(0, traj.end+1) :
            
            mean_prop[it, iobj, r1] = np.mean(data[it, :, :], axis=0)  
            mean_prop[it, iobj, r2] = np.mean(derv_data[it, :, :], axis=0)    
            mean_prop[it, iobj, r3] = np.mean(tr[it, :, :], axis=0)
            mean_prop[it, iobj, r4] = np.size(data[it, :, 0])
            
            for iclass in range(0,n_class) :
#                if debug_mean : 
#                    print(it, iclass)
                trcl = traj_class[it, obj_ptrs]
                lmask = (trcl == iclass)  
                where_mask = np.where(lmask)[0]
         
                if np.size(where_mask) > 0 :
#                    if debug_mean : 
#                        print(data[it, lmask, :])
#                        print(derv_data[it, lmask, :])
                    mean_prop_by_class[it, iobj, r1, iclass] = \
                        np.sum(data[it, lmask, :], axis=0)  
                    mean_prop_by_class[it, iobj, r2, iclass] = \
                        np.sum(derv_data[it, lmask, :], axis=0)    
                    mean_prop_by_class[it, iobj, r3, iclass] = \
                        np.sum(tr[it, lmask,:], axis=0)
                    mean_prop_by_class[it, iobj, r4, iclass] = \
                        np.size(where_mask)
                        
# Now compute budget and entrainment/detrainment terms.

        delta_t = (traj.times[1:]-traj.times[:-1])
                        
        incloud = np.arange(traj.end + 1, dtype=int)
        incloud = np.logical_and( \
                        incloud >= traj_cl['cloud_trigger_time'][iobj],\
                        incloud <  traj_cl['cloud_dissipate_time'][iobj])
        
        precloud = np.arange(traj.end + 1, dtype=int)
        precloud = (precloud < traj_cl['cloud_trigger_time'][iobj])
#            print(precloud)
# Cloud volume
        v_main_cloud = mean_prop_by_class[:,iobj,:npts_ptr, CLOUD] + \
                       mean_prop_by_class[:,iobj,:npts_ptr, ENTR_FROM_ABOVE_BL] + \
                       mean_prop_by_class[:,iobj,:npts_ptr, ENTR_FROM_BL]
                       
        n_main_cloud = mean_prop_by_class[:,iobj, npts_ptr, CLOUD] + \
                       mean_prop_by_class[:,iobj, npts_ptr, ENTR_FROM_ABOVE_BL] + \
                       mean_prop_by_class[:,iobj, npts_ptr, ENTR_FROM_BL]
                       
        incl = (n_main_cloud > 0)
        z_cloud = (v_main_cloud[:, z_ptr]-0.5)*traj.deltaz
#        print(np.shape(z_cloud), np.shape(n_main_cloud),np.shape(incl))
        z_cloud[incl] = z_cloud[incl] / n_main_cloud[incl]          

        if debug_mean :
            print(traj_cl['cloud_trigger_time'][iobj],traj_cl['cloud_dissipate_time'][iobj])
            print(np.shape(incloud),np.shape(precloud))
            print(mean_prop_by_class[:, iobj, npts_ptr, CLOUD])
            print(precloud)
            print(incloud)
            print(incl)
            print(z_cloud)
                      
        cloud_volume = n_main_cloud * grid_box_volume 

        cloud_prop[:,iobj,CLOUD_HEIGHT] = z_cloud
        cloud_prop[:,iobj,CLOUD_POINTS] = n_main_cloud
        cloud_prop[:,iobj,CLOUD_VOLUME] = cloud_volume
        
##################### Lagrangian budget #####################################        

# Budget:
# This timestep
# (In cloud or prev cloud now and not new) +
# (Just entrained at cloud base) +
# (Just entrained above cloud base) +
# (Just detrained)
# 
# Where did this come from?
# Previous timestep
# (In cloud or prev cloud now and not new) +
# (Just entrained at cloud base) +
# (Just entrained above cloud base) +
# -(Change in pre cloud entrained at cloud base) +
# -(Change in pre cloud entrained above cloud base) +
# -(Change in post detrained if negative)
# -(Change in post detrained previous cloud if negative)
#   
################### This timestep ###########################
#            
# In cloud now and not new.
        v_now  = mean_prop_by_class[1:,iobj,:npts_ptr, CLOUD] 
        n_now  = mean_prop_by_class[1:,iobj, npts_ptr, CLOUD]

# In prev cloud now and not new.
        v_prev_now  = mean_prop_by_class[1:,iobj,:npts_ptr, PREVIOUS_CLOUD]
        n_prev_now  = mean_prop_by_class[1:,iobj, npts_ptr, PREVIOUS_CLOUD]
  
# New cloud entrained from cloud base                 
        v_entr_bot = mean_prop_by_class[1:,iobj,:npts_ptr, ENTR_FROM_BL]
        n_entr_bot = mean_prop_by_class[1:,iobj, npts_ptr, ENTR_FROM_BL]

# New cloud entrained from above cloud base                               
        v_entr = mean_prop_by_class[1:,iobj,:npts_ptr, ENTR_FROM_ABOVE_BL]
        n_entr = mean_prop_by_class[1:,iobj, npts_ptr, ENTR_FROM_ABOVE_BL]

# Just detrained.
        v_detr = mean_prop_by_class[1:,iobj,:npts_ptr, DETRAINED] + \
                 mean_prop_by_class[1:,iobj,:npts_ptr, DETR_PREV]
        n_detr = mean_prop_by_class[1:,iobj, npts_ptr, DETRAINED] + \
                 mean_prop_by_class[1:,iobj, npts_ptr, DETR_PREV]

################### Previous timestep ###########################
#
# (In cloud or prev cloud now and not new) +
# (Just entrained at cloud base) +
# (Just entrained above cloud base) 
                 
        v_prev = mean_prop_by_class[:-1,iobj,:npts_ptr, CLOUD] + \
                 mean_prop_by_class[:-1,iobj,:npts_ptr, PREVIOUS_CLOUD]+ \
                 mean_prop_by_class[:-1,iobj,:npts_ptr, ENTR_FROM_ABOVE_BL] + \
                 mean_prop_by_class[:-1,iobj,:npts_ptr, ENTR_FROM_BL] 
        n_prev = mean_prop_by_class[:-1,iobj, npts_ptr, CLOUD] + \
                 mean_prop_by_class[:-1,iobj, npts_ptr, PREVIOUS_CLOUD] + \
                 mean_prop_by_class[:-1,iobj, npts_ptr, ENTR_FROM_ABOVE_BL] + \
                 mean_prop_by_class[:-1,iobj, npts_ptr, ENTR_FROM_BL]

# (Change in pre cloud entrained at cloud base)

        v_entr_pre_bot = mean_prop_by_class[ :-1,iobj,:npts_ptr, PRE_CLOUD_ENTR_FROM_BL] - \
                         mean_prop_by_class[1:,  iobj,:npts_ptr, PRE_CLOUD_ENTR_FROM_BL]
        n_entr_pre_bot = mean_prop_by_class[ :-1,iobj, npts_ptr, PRE_CLOUD_ENTR_FROM_BL] - \
                         mean_prop_by_class[1:,  iobj, npts_ptr, PRE_CLOUD_ENTR_FROM_BL]
                        
# (Change in pre cloud entrained above cloud base)
        v_entr_pre = mean_prop_by_class[ :-1,iobj,:npts_ptr, PRE_CLOUD_ENTR_FROM_ABOVE_BL] - \
                     mean_prop_by_class[1:,  iobj,:npts_ptr, PRE_CLOUD_ENTR_FROM_ABOVE_BL]
        n_entr_pre = mean_prop_by_class[ :-1,iobj, npts_ptr, PRE_CLOUD_ENTR_FROM_ABOVE_BL] - \
                     mean_prop_by_class[1:,  iobj, npts_ptr, PRE_CLOUD_ENTR_FROM_ABOVE_BL]
                                                      
                           
# Decrease in air detrained from previous cloud.       
# (Change in post detrained previous cloud if negative)
        v_entr_prev_cl = mean_prop_by_class[1:  ,iobj,:npts_ptr, POST_DETR_PREV] - \
                         mean_prop_by_class[ :-1,iobj,:npts_ptr, POST_DETR_PREV]
        n_entr_prev_cl = mean_prop_by_class[1:  ,iobj, npts_ptr, POST_DETR_PREV] - \
                         mean_prop_by_class[ :-1,iobj, npts_ptr, POST_DETR_PREV]
                         
        prev_cl_not_entr = (n_entr_prev_cl > 0)[...,0]
        v_entr_prev_cl[prev_cl_not_entr,:] = 0
        n_entr_prev_cl[prev_cl_not_entr,:] = 0

# -(Change in post detrained if negative)
        v_entr_detr_cl = mean_prop_by_class[1:  ,iobj,:npts_ptr, POST_DETR] - \
                         mean_prop_by_class[ :-1,iobj,:npts_ptr, POST_DETR]
        n_entr_detr_cl = mean_prop_by_class[1:  ,iobj, npts_ptr, POST_DETR] - \
                         mean_prop_by_class[ :-1,iobj, npts_ptr, POST_DETR]

        detr_cl_not_entr = (n_entr_detr_cl > 0)[...,0]
        v_entr_detr_cl[detr_cl_not_entr,:] = 0
        n_entr_detr_cl[detr_cl_not_entr,:] = 0
                         
        n_now = n_now[:, np.newaxis]
        n_prev_now = n_prev_now[:, np.newaxis]
        n_entr_bot = n_entr_bot[:, np.newaxis]
        n_entr = n_entr[:, np.newaxis]
        n_detr = n_detr[:, np.newaxis]
        n_prev = n_prev[:, np.newaxis]
        n_entr_pre_bot = n_entr_pre_bot[:, np.newaxis]
        n_entr_pre = n_entr_pre[:, np.newaxis]
        n_entr_prev_cl = n_entr_prev_cl[:, np.newaxis]
        n_entr_detr_cl = n_entr_detr_cl[:, np.newaxis]


#        if debug_mean : 
#            print('entr_bot_pre', v_entr_pre_bot[..., mse_ptr ],n_entr_pre_bot)
        
        v_total_now = v_now + v_prev_now + v_entr + v_entr_bot + v_detr 
        n_total_now = n_now + n_prev_now + n_entr + n_entr_bot + n_detr
        
#        if debug_mean : 
#            print('v_total_now', v_total_now[..., mse_ptr ],n_total_now)
        
        v_total_pre = v_prev + v_entr_pre + v_entr_pre_bot \
                      - v_entr_prev_cl - v_entr_detr_cl
        n_total_pre = n_prev + n_entr_pre + n_entr_pre_bot \
                      - n_entr_prev_cl - n_entr_detr_cl
        
#        if debug_mean : 
#            print('v_total_pre', v_total_pre[..., mse_ptr ],n_total_pre)
                                                                      
        v_loss = v_total_now - v_total_pre 
        n_loss = n_total_now - n_total_pre
        
        if debug_mean : 
#            print('now',v_now[..., mse_ptr],n_now )

            print('loss', v_loss[..., mse_ptr])
        
        some_cl = n_total_now[:,0] > 0
        v_loss_cl = np.zeros_like(v_loss) 
        v_loss_cl[some_cl] = v_loss[some_cl] / n_total_now[some_cl]

        if debug_mean : 
#            print('now',v_now[..., mse_ptr],n_now )

            print('loss', v_loss_cl[..., mse_ptr])
#        print(np.shape(some_cl), np.shape(v_loss), np.shape(n_total_now))                  
        
        if debug_mean : 
#            print('loss per point', v_loss[..., mse_ptr ])
            ln = "{:3d} "
            for i in range(11) : ln += "{:5.0f} "
            print(" i    now  prev e_bot   ent   det n_pre  pe_b    pe    pp     ep nloss")
            for i in range(np.shape(v_now)[0]) :
                print(ln.format(i+1, n_now[i,0], \
                                     n_prev_now[i,0], \
                                     n_entr_bot[i,0], \
                                     n_entr[i,0], \
                                     n_detr[i,0], \
                                     n_prev[i,0], \
                                     n_entr_pre_bot[i,0], \
                                     n_entr_pre[i,0], \
                                     n_entr_prev_cl[i,0], \
                                     n_entr_detr_cl[i,0], \
                                     n_loss[i,0]))
# Detrainment rate
        
        if False : 
            print("n_detr",np.shape(n_detr))
            print("n_entr",np.shape(n_entr))
            print("n_entr_bot",np.shape(n_entr_bot))
            
# Detrainment rate
        
        n_cloud = n_now + (n_entr + n_entr_bot + n_detr) / 2.0
        some_cl = (n_cloud[:,0] > 0)
        w = mean_prop_by_class[1:, iobj, w_ptr, CLOUD] + \
            (mean_prop_by_class[1:, iobj, w_ptr, ENTR_FROM_ABOVE_BL] + \
             mean_prop_by_class[1:, iobj, w_ptr, ENTR_FROM_BL] + \
             mean_prop_by_class[1:, iobj, w_ptr, DETRAINED]) / 2.0 
            
#        print(np.shape(some_cl), np.shape(w), np.shape(n_cloud))                  
        w_cloud = np.zeros_like(w)
        w_cloud[some_cl] = w[some_cl] / n_cloud[some_cl,0]
        
        delta_n_over_n = np.zeros_like(n_cloud[:,0])
        delta_n_over_n[some_cl] = n_detr[some_cl,0] / n_cloud[some_cl,0]
#        print(np.shape(delta_n_over_n),np.shape(delta_t))
        detr_rate = delta_n_over_n / delta_t
# Detrainment rate per m
             
#        print(np.shape(some_cl), np.shape(w_cloud), np.shape(detr_rate))                  
        detr_rate_z = np.zeros_like(detr_rate)
        detr_rate_z[some_cl] = detr_rate[some_cl] / w_cloud[some_cl]
            
# Total Entrainment rate
        n_new_cloud = n_entr + n_entr_bot 
        delta_n_over_n = np.zeros_like(n_cloud[:,0])
        delta_n_over_n[some_cl] = n_new_cloud[some_cl,0] / n_cloud[some_cl,0]                
        entr_rate_tot = delta_n_over_n / delta_t
                        
# Entrainment rate per m      
             
        entr_rate_tot_z = np.zeros_like(entr_rate_tot)
        entr_rate_tot_z[some_cl] = entr_rate_tot[some_cl] / w_cloud[some_cl]
        
# Side Entrainment rate 
        n_new_cloud = n_entr 
        delta_n_over_n = np.zeros_like(n_cloud[:,0])
        delta_n_over_n[some_cl] = n_new_cloud[some_cl,0] / n_cloud[some_cl,0]
        
        z1 = (mean_prop_by_class[1:, iobj, z_ptr, CLOUD]-0.5)*traj.deltaz 
        
        
        entr_rate = delta_n_over_n / delta_t
# Side Entrainment rate per m
             
        entr_rate_z = np.zeros_like(entr_rate)
        entr_rate_z[some_cl] = entr_rate[some_cl] / w_cloud[some_cl]
        
# Cloud_base Entrainment_rate 
        n_new_cloud = n_entr_bot 
        delta_n_over_n = np.zeros_like(n_cloud[:,0])
        delta_n_over_n[some_cl] = n_new_cloud[some_cl,0] / n_cloud[some_cl,0]                
        entr_rate_cb = delta_n_over_n / delta_t

# Cloud_base Entrainment_rate per m 
        entr_rate_cb_z = np.zeros_like(entr_rate)
        entr_rate_cb_z[some_cl] = entr_rate_cb[some_cl] / w_cloud[some_cl]
        
        if False : 
            print('n cloud', n_cloud)
            print('w cloud', mean_prop_by_class[1:, iobj, w_ptr, CLOUD])
            print('w entr', mean_prop_by_class[1:, iobj, w_ptr, ENTR_FROM_ABOVE_BL])
            print('w', w)


        if False : 
            print('detr_rate', np.shape(detr_rate))
            print('entr_rate_tot', np.shape(entr_rate_tot))
            print('entr_rate', np.shape(entr_rate))

        if debug_mean : 
            print('detr_rate', detr_rate)
            print('detr_rate_z', detr_rate_z)
            print('entr_rate_tot', entr_rate_tot)
            print('entr_rate_tot_z', entr_rate_tot_z)
            print('entr_rate', entr_rate)
            print('entr_rate_z', entr_rate_z)
            
            
#        print(np.shape(v_loss), np.shape(budget_loss[:,iobj,:]))
#        budget_loss[:,iobj,:] = v_loss_cl
        budget_loss[:, iobj, :] = mean_prop[1:  , iobj, :-1] - \
                                  mean_prop[ :-1, iobj, :-1]

        entrainment[:, iobj, TOT_ENTR] = entr_rate_tot
        entrainment[:, iobj, TOT_ENTR_Z] = entr_rate_tot_z
            
        entrainment[:, iobj, SIDE_ENTR] = entr_rate
        entrainment[:, iobj, SIDE_ENTR_Z] = entr_rate_z

        entrainment[:, iobj, CB_ENTR] = entr_rate_cb
        entrainment[:, iobj, CB_ENTR_Z] = entr_rate_cb_z

        entrainment[:, iobj, DETR] = detr_rate
        entrainment[:, iobj, DETR_Z] = detr_rate_z
        
# Overall cloud properties
# Cloud base
        max_cloud_base_area[iobj] = np.max(n_entr_bot)
#        print(max_cloud_base_area[iobj])
#        print(np.where(n_entr_bot == max_cloud_base_area[iobj])[0][0])
        max_cloud_base_time[iobj] = np.where(n_entr_bot == max_cloud_base_area[iobj])[0][0]
#        print(max_cloud_base_time[iobj])
        if max_cloud_base_area[iobj] > 0 :
            cloud_base_variables[iobj,:] = v_entr_bot[max_cloud_base_time[iobj], :] / max_cloud_base_area[iobj]
        else :
           print('Zero cloud base area for cloud {}'.format(iobj))
        max_cloud_base_area[iobj] = max_cloud_base_area[iobj] * grid_box_area
           
#        nplt = 72
#        for it in range(np.shape(mean_prop_by_class)[0]) :
#            s = '{:3d}'.format(it)
#            for iclass in range(0,n_class) :
#                s = s+'{:4d} '.format(mean_prop_by_class[it, nplt, r4, iclass].astype(int))
#            s = s+'{:6d} '.format(np.sum(mean_prop_by_class[it, nplt, r4, :].astype(int)))
#            print(s)
#            
#        for it in range(np.shape(mean_prop_by_class)[0]) :
#            s = '{:3d}'.format(it)
#            for iclass in range(0,n_class) :
#                s = s+'{:10f} '.format(mean_prop_by_class[it, nplt, nvars, iclass]/1E6)
#            s = s+'{:12f} '.format(np.sum(mean_prop_by_class[it, nplt, nvars, :])/1E6)
#            print(s)
        
    for iclass in range(0,n_class) :
        m = (mean_prop_by_class[:, :, r4, iclass]>0)   
        for ii in range(nvars+ndvars+nposvars) : 
            mean_prop_by_class[:, :, ii, iclass][m] /= \
                mean_prop_by_class[:, :, r4, iclass][m]
                

    mean_properties = {"overall_mean":mean_prop, \
                       "unclassified":mean_prop_by_class[..., UNCLASSIFIED], \
                       "pre_cloud_bl":mean_prop_by_class[..., PRE_CLOUD_ENTR_FROM_BL], \
                       "pre_cloud_above_bl":mean_prop_by_class[..., PRE_CLOUD_ENTR_FROM_ABOVE_BL], \
                       "previous_cloud":mean_prop_by_class[..., PREVIOUS_CLOUD], \
                       "detr_prev":mean_prop_by_class[..., DETR_PREV], \
                       "post_detr_prev":mean_prop_by_class[..., POST_DETR_PREV], \
                       "cloud":mean_prop_by_class[..., CLOUD], \
                       "entr_bot":mean_prop_by_class[..., ENTR_FROM_BL], \
                       "entr":mean_prop_by_class[..., ENTR_FROM_ABOVE_BL], \
                       "detr":mean_prop_by_class[..., DETRAINED], \
                       "post_detr":mean_prop_by_class[..., DETRAINED], \
                       "subsequent_cloud":mean_prop_by_class[..., SUBSEQUENT_CLOUD], \
                       "cloud_properties":cloud_prop, \
                       "budget_loss":budget_loss, \
                       "entrainment":entrainment, \
                       "max_cloud_base_area":max_cloud_base_area, \
                       "max_cloud_base_time":max_cloud_base_time, \
                       "cloud_base_variables":cloud_base_variables, \
                       "derived_variable_list":derived_variable_list, \
                       }

    return mean_properties
            
def trajectory_cloud_ref(dataset, time_index, thresh=0.00001) :
    """
    Function to set up origin of back and forward trajectories.

    Args:
        dataset        : Netcdf file handle.
        time_index     : Index of required time in file.
        thresh=0.00001 : Cloud liquid water threshold for clouds.

    Returns: 
        Trajectory variables::
        
            traj_pos       : position of origin point.
            labels         : array of point labels.
            nobjects       : number of objects.

    @author: Peter Clark

    """
    
#    print(dataset)
#    print(time_index)
#    print(thresh)
    data = dataset.variables["q_cloud_liquid_mass"][time_index, ...]
    
    xcoord = np.arange(np.shape(data)[0],dtype='float')
    ycoord = np.arange(np.shape(data)[1],dtype='float')
    zcoord = np.arange(np.shape(data)[2],dtype='float')
    
    logical_pos = cloud_select(data, thresh=thresh)
    
#    print('q_cl threshold {:10.6f}'.format(np.max(data[...])*0.8))
    
    mask = np.zeros_like(data)
    mask[logical_pos] = 1

    print('Setting labels.')
    labels, nobjects = label_3D_cyclic(mask)
    
    labels = labels[logical_pos]
    
    pos = np.where(logical_pos)
    
#    print(np.shape(pos))
    traj_pos = np.array( [xcoord[pos[0][:]], \
                          ycoord[pos[1][:]], \
                          zcoord[pos[2][:]]],ndmin=2 ).T

                                
    return traj_pos, labels, nobjects
   
def in_cloud(traj, *argv, thresh=1.0E-5) :
    """
    Function to select trajectory points inside cloud.
    In general, 'in-object' identifier should return a logical mask and a 
    quantitative array indicating an 'in-object' scalar for use in deciding
    reference times for the object.
    
    Args:
        traj           : Trajectory object.
        tr_time        : Time index (optional)
        obj_ptrs       : Logical array selecting object
        thresh=0.00001 : Cloud liquid water threshold for clouds.

    Returns:
        Variables defining those points in cloud::
        
            mask           : Logical array like trajectory array.
            qcl            : Cloud liquid water content array.

    @author: Peter Clark

    """
    data = traj.data    
    v = traj.var("q_cloud_liquid_mass")
    
    if len(argv) == 2 :
        (tr_time, obj_ptrs) = argv
        qcl = data[ tr_time, obj_ptrs, v]
    else :
        qcl = data[..., v]

#    mask = data[...]>(np.max(data[...])*0.6)
    mask = cloud_select(qcl, thresh=thresh)
    return mask, qcl

def cloud_select(qcl, thresh=1.0E-5) :
    """
    Simple function to select in-cloud data; 
    used in in_cloud and trajectory_cloud_ref for consistency.
    Written as a function to set structure for more complex object identifiers.
    
    Args:
        qcl            : Cloud liquid water content array.
        thresh=0.00001 : Cloud liquid water threshold for clouds.

    Returns: 
        Logical array like trajectory array selecting those points inside cloud.

    @author: Peter Clark

    """
    
    mask = qcl >= thresh
    return mask
