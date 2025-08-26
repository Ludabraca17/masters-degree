var namespace;
var cssParser = new cssjs();

self.onInit = function() {
    var scope = self.ctx.$scope;

    // Check if the $scope is initialized
    if (!scope) {
        console.error("Scope is not available yet.");
        return;
    }

    // Initialize attributes object if it doesn't exist
    scope.attributes = scope.attributes || {}; // Initialize if not defined
    scope.pendingChanges = {};  // Track pending changes

    // Load all shared attributes dynamically
    self.ctx.attributeService.getEntityAttributes(self.ctx.entityId, 'SHARED_SCOPE')
        .subscribe(
            function success(attributes) {
                attributes.forEach(attr => {
                    scope.attributes[attr.key] = attr.value;
                });
                console.log("Loaded Shared Attributes:", scope.attributes);
                self.ctx.detectChanges();  // Trigger change detection after loading attributes
            },
            function error(err) {
                console.error("Failed to load shared attributes:", err);
            }
        );

    // Force a change detection cycle to make sure the UI updates
    self.ctx.detectChanges();
};

// Function to toggle the attribute value
self.ctx.$scope.toggleAttribute = function(attribute) {
    var scope = self.ctx.$scope;

    // Ensure scope and attributes are properly initialized
    if (!scope || !scope.attributes) {
        console.error("Scope or attributes are not properly initialized.");
        return;
    }

    // Ensure the attribute exists before toggling
    if (scope.attributes[attribute] !== undefined) {
        var currentState = scope.attributes[attribute];
        var newState = getNextState(currentState);  // Get the next state in the cycle
        scope.attributes[attribute] = newState;  // Update the attribute
        console.log(attribute + " toggled to " + newState);
    } else {
        console.error("Attribute not found: " + attribute);
    }

    // Mark this attribute as pending for future updates
    scope.pendingChanges[attribute] = true;
};

// Helper function to cycle through states (green, blue, red, yellow)
function getNextState(currentState) {
    switch (currentState) {
        case 'green': return 'blue';
        case 'blue': return 'red';
        case 'red': return 'yellow';
        case 'yellow': return 'green';
        default: return 'green';  // Default to green if state is unknown
    }
}

// Function to apply all pending changes at once
self.ctx.$scope.updateAttributes = function() {
    var scope = self.ctx.$scope;

    // Ensure scope and attributes are properly initialized
    if (!scope || !scope.attributes) {
        console.error("Scope or attributes are not properly initialized.");
        return;
    }

    var updates = {};

    // Collect all attributes that have been toggled
    for (var attribute in scope.pendingChanges) {
        if (scope.pendingChanges[attribute]) {
            updates[attribute] = scope.attributes[attribute];
        }
    }

    // Update all the toggled attributes at once
    if (Object.keys(updates).length > 0) {
        self.ctx.controlApi.saveEntityAttributes(scope.entityId, 'SHARED_SCOPE', updates)
            .subscribe(
                function success(response) {
                    console.log("Attributes updated successfully:", response);
                    scope.pendingChanges = {};  // Clear pending changes after updating
                    self.ctx.detectChanges();  // Trigger change detection
                },
                function error(err) {
                    console.error("Failed to update attributes:", err);
                }
            );
    }
};
