#---------------------------------------------------------------------------------
# Ultima 6 SNES Port Makefile
#---------------------------------------------------------------------------------

ifeq ($(strip $(PVSNESLIB_HOME)),)
$(error "Please set PVSNESLIB_HOME in your environment. e.g. export PVSNESLIB_HOME=/d/pvsneslib")
endif

# Include PVSnesLib rules
include $(PVSNESLIB_HOME)/devkitsnes/snes_rules

OUTPUT = ultima6_snes
CFILES = src/main.c
SFILES = 

all: $(OUTPUT).sfc

$(OUTPUT).sfc: $(CFILES)
	@echo "Building Ultima 6 SNES..."
	$(CC) $(CFILES)
	$(LNK) $(OUTPUT).fig
	$(FIX) $(OUTPUT).sfc

clean:
	@echo "Cleaning project..."
	rm -f *.sfc *.fig *.o *.sym src/*.o
