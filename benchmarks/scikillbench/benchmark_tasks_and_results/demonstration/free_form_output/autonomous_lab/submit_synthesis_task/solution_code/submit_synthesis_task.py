"""
AlabOS experiment submission system
"""
import os
import sys
import time
import traceback
from functools import cached_property
from typing import List, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from pymatgen.core import Composition

# Set environment variables
os.environ['SIM_MODE_FLAG'] = 'TRUE'
os.environ['ALABOS_CONFIG_PATH'] = os.getenv('ALABOS_CONFIG_PATH')

# Add alab-gpss to Python path if ALAB_GPSS_FILE_PATH is set
alab_gpss_path = os.getenv('ALAB_GPSS_FILE_PATH')
if alab_gpss_path and os.path.exists(alab_gpss_path):
    sys.path.insert(0, alab_gpss_path)

# Import AlabOS components
from alab_management.builders import ExperimentBuilder
from alab_gpss.system.tasks.add_sample import GPSSAddSample
from alab_gpss.system.tasks.heating import GPSSHeating
from alab_gpss.system.tasks.powder_dispensing import GPSSPowderDispensing
from alab_gpss.system.tasks.powder_mixing import GPSSPowderMixing
from alab_gpss.system.tasks.remove_sample import RemoveSample
from alab_gpss.system.tasks.sample_grinding_xrd import GPSSSampleGrindingXRD
from alab_gpss.experiment_design.reactions.balance import generate_recipe

def to_tuple(obj):
    """Convert a nested list to a tuple"""
    if isinstance(obj, list):
        return tuple(to_tuple(item) for item in obj)
    return obj


class Sample(BaseModel):
    """Sample model for experiment"""
    composition: str = Field(description="The chemical composition of the sample. Must be a valid composition string.")
    heating_temperature: List[int] = Field(
        min_items=1,
        max_items=8,
        description="The heating temperatures of the sample. It is a list of segments. Must be a list of integers between 0 and 1000.",
    )
    heating_time_hour: List[float] = Field(
        min_items=1,
        max_items=8,
        description="The heating time of the sample. It is a list of segments of the heating process. Must be a list of floats between 0 and 24.",
    )
    heating_ramping_rate: Union[List[float], float] = Field(
        default=2,
        description="The heating ramping rate of the sample. It is a list of segments of the heating process. Must be a list of floats between 0 and 10. If a single float is provided, it will be used for all segments.",
    )
    precursors: List[str] = Field(description="The precursors of the sample. Must be a list of strings.")

    @field_validator("composition")
    def validate_composition(cls, v):
        try:
            Composition(v)
        except Exception as e:
            raise ValueError(f"Invalid composition '{v}': {e}")
        return v

    @field_validator("heating_temperature")
    def validate_heating_temperature(cls, v):
        for temp in v:
            if not (0 <= temp <= 1000):
                raise ValueError(f"Heating temperature {temp} must be between 0 and 1000")
        return v

    @field_validator("heating_time_hour")
    def validate_heating_time_hour(cls, v):
        for time in v:
            if not (0 <= time <= 24):
                raise ValueError(f"Heating time {time} must be between 0 and 24")
        return v

    @field_validator("heating_ramping_rate")
    def validate_heating_ramping_rate(cls, v):
        if isinstance(v, list):
            for rate in v:
                if not (0 <= rate <= 10):
                    raise ValueError(f"Heating ramping rate {rate} must be between 0 and 10")
        elif not (0 <= v <= 10):
            raise ValueError(f"Heating ramping rate {v} must be between 0 and 10")
        return v

    @model_validator(mode="after")
    def validate_all(self):
        if isinstance(self.heating_ramping_rate, (int, float)):
            self.heating_ramping_rate = [self.heating_ramping_rate] * len(self.heating_temperature)
        if len(self.heating_temperature) != len(self.heating_time_hour) or len(self.heating_temperature) != len(self.heating_ramping_rate):
            raise ValueError("Heating temperature, time, and ramping rate must have the same length")
        return self

    @cached_property
    def heating_profile(self):
        temperature_profile = []
        for temp, time, rate in zip(self.heating_temperature, self.heating_time_hour, self.heating_ramping_rate):
            temperature_profile.append((temp, rate, time * 60))
        return to_tuple(temperature_profile)


class Experiment(BaseModel):
    """Experiment model"""
    samples: List[Sample] = Field(
        min_items=1, max_items=8, description="The samples of the experiment. Must be a list of samples."
    )
    project_name: str = Field(description="The name of the project. Must be a string.", default="halide_project")

    def make_experiment(self) -> ExperimentBuilder:
        today = time.strftime("%m%d%y")

        exp = ExperimentBuilder(name=f"{self.project_name}_{today}", tags=["submission"])

        # group by heating profile
        heating_profile_groups = {}
        for sample in self.samples:
            if sample.heating_profile not in heating_profile_groups:
                heating_profile_groups[sample.heating_profile] = []
            heating_profile_groups[sample.heating_profile].append(sample)

        for heating_profile, samples in heating_profile_groups.items():
            all_sample_builders = []
            for sample in samples:
                sample_builder = exp.add_sample(
                    name=f"{sample.composition.replace('.', 'p')}_{today}", tags=["submission"]
                )
                recipe = generate_recipe(sample.composition, sample.precursors, target_mass_g=0.5)
                add_sample = GPSSAddSample(notify_user=False)
                add_sample.add_to(sample_builder)
                powder_dispensing = GPSSPowderDispensing({p.name: p.mass for p in recipe.precursors}, 1, num_balls=4)
                powder_dispensing.add_to(sample_builder)
                powder_mixing = GPSSPowderMixing([1000, 1500], [300, 300], interval_seconds=30)
                powder_mixing.add_to(sample_builder)
                all_sample_builders.append(sample_builder)

            heating = GPSSHeating(heating_profile)
            heating.add_to(all_sample_builders)

            for sample_builder in all_sample_builders:
                sample_grinding_xrd = GPSSSampleGrindingXRD(360, 28)
                sample_grinding_xrd.add_to(sample_builder)
                remove_sample = RemoveSample()
                remove_sample.add_to(sample_builder)

        return exp


def submit_experiment(samples: List[Sample], project_name: str = "halide_project") -> str:
    """
    Submit experiment to the lab system.
    Returns confirmation string.

    Args:
        samples: List[Sample]. The samples to submit.
        project_name: str. The name of the project.

    Returns:
        str: A confirmation string.

    Example:
        submit_experiment(samples=[Sample(composition="NaCl", precursors=["Na", "Cl"])], project_name="halide_project")
    """
    try:
        exp_builder = Experiment(samples=samples, project_name=project_name).make_experiment()
        exp_builder.submit()
        return f"✅ Experiment ({exp_builder.name}) submitted!"
    except Exception as e:
        print(traceback.format_exc())
        return f"❌ Error submitting experiment: {traceback.format_exc()}"

if __name__ == "__main__":
    
    # Here we add FeCl3 to the precursors to avoid the error of alab-gpss not being able to auto-balance the reaction. A better solution is to use the fallback as the agent's solution to a stoichiometric calculation
    sample = Sample(
        composition="Li2Fe0.8Ni0.2Cl4",
        precursors=["LiCl", "FeCl2", "FeCl3","NiCl2"],
        heating_temperature=[450],
        heating_time_hour=[12],
        heating_ramping_rate=[2]
    )
    
    result = submit_experiment([sample], "halide_project")
    print(result)