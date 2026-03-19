# System Architecture

Data flow and model chain for the Gorzen digital twin platform.

## Data Flow

```mermaid
flowchart LR
    DataInput[Operator Input] --> Preprocess[Preprocessing Module]
    Preprocess --> Models[Physical Models]
    Models --> Envelope[Envelope Solver]
    Envelope --> Report[Flight Plan / Output]
```

## Model Chain (17 Models)

```mermaid
flowchart TB
    subgraph Input
        Twin[Twin Config]
        Mission[Mission Profile]
    end

    subgraph Environment
        Env[Environment Model]
    end

    subgraph Propulsion
        Air[Airframe]
        ICE[ICE Engine]
        Fuel[Fuel System]
        Rotor[Rotor]
        Motor[Motor]
        ESC[ESC]
        Batt[Battery]
        Gen[Generator]
    end

    subgraph Perception
        Avionics[Avionics]
        Compute[Compute]
        Comms[Comms]
        GSD[GSD]
        Blur[Motion Blur]
        RS[Rolling Shutter]
        IQ[Image Quality]
        Ident[Identification]
    end

    Twin --> Env
    Mission --> Env
    Env --> Air
    Air --> ICE
    ICE --> Fuel
    Air --> Rotor
    Rotor --> Motor
    Motor --> ESC
    ESC --> Batt
    ICE --> Gen
    Gen --> Batt
    Env --> Avionics
    Avionics --> Compute
    Avionics --> Comms
    Env --> GSD
    GSD --> Blur
    Blur --> RS
    RS --> IQ
    IQ --> Ident
    Comms --> Ident
    Compute --> Ident
```

## Envelope Solver Pipeline

```mermaid
flowchart LR
    Grid[Speed × Altitude Grid] --> Eval[Per-Point Evaluation]
    Eval --> Chain[17-Model Chain]
    Chain --> Feas[Feasibility Mask]
    Feas --> UQ[UQ Propagation]
    UQ --> MCP[Mission Completion Probability]
    MCP --> Output[Envelope Response]
```

## API Structure

```mermaid
flowchart TB
    Client[Frontend / Client] --> API[FastAPI]
    API --> TwinRouter[/twin]
    API --> EnvelopeRouter[/envelope]
    API --> MissionRouter[/mission]
    API --> CatalogRouter[/catalog]
    TwinRouter --> Solver[Envelope Solver]
    EnvelopeRouter --> Solver
    MissionRouter --> Solver
```
