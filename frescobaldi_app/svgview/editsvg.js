/*************************************************************************** 
* This file is part of the Frescobaldi project, http://www.frescobaldi.org/
*
* Copyright (c) 2008 - 2012 by Wilbert Berendsen
*
* This program is free software; you can redistribute it and/or
* modify it under the terms of the GNU General Public License
* as published by the Free Software Foundation; either version 2
* of the License, or (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with this program; if not, write to the Free Software
* Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
* See http://www.gnu.org/licenses/ for more information.
*/
window.addEventListener('error', error, false); 

var objTransform;
var svgarr = document.getElementsByTagName("svg");
var svg = svgarr[0];
var maxX = svg.offsetWidth-1;
var maxY = svg.offsetHeight-1;
var draggable = document.getElementsByTagName('a');
var draggedObject, dragOrigin, dragPos = null;

var clone, delNode;

// object and helper positioning variables
// should be put into an object.

// "init" = the positions generated by LilyPond
var initX, initY;
// position of the object at the start of the drag
var startX, startY;
// current position of the object
var currX, currY;
// offset against init position when starting the drag
var startOffX, startOffY;
// current offset of the object relative to the init position
var currOffX, currOffY;


//listen for drag events on all text elements
//and save their initial position
for (var t= 0; t < draggable.length; ++t){
	
	var node = draggable[t].firstChild;
	
	//loop through the children of every draggable node
	while(node){		
		// so far only enable dragging of 
		// nodes with the transform attribute
		if(node.nodeType==1 && node.hasAttribute("transform")){

			enableMouseEvents(node);
			
			var doSave = pyLinks.savePos();

			if (doSave){
				var p = getTranslPos(node);	
				node.setAttribute("init-x",p.x);
				node.setAttribute("init-y",p.y);
			}			
		}
		node = node.nextSibling;
	}
}

pyLinks.setSaved();

//write error message
function error(e){
	pyLinks.pyLog(e.message);
}

function enableMouseEvents(elem){
	elem.onmousedown = MouseDown;
	elem.onmousemove = MouseMove;
	elem.onmouseup = MouseUp;
}

function calcPositions(e){
    // calculate all the necessary values while dragging
    // these should better be properties of an object
    // because many of them don't have to be stored as values.
    dragPos = mousePos(e);
    // current offset of the dragging operation itself
    dragOffX = getRoundDiffPos(dragPos.x, dragOrigin.x);
    dragOffY = getRoundDiffPos(dragPos.y, dragOrigin.y);
    // current position of the object
    currX = startX + dragOffX;
    currY = startY + dragOffY;
    // current offset of the object against its init position
    currOffX = startOffX + dragOffX;
    currOffY = startOffY - dragOffY;
}

function MouseDown(e){
  e.stopPropagation();
  // Set flags and values for the drag operation
  draggedObject = e.target;
  dragOrigin = mousePos(e);

  // load original (LilyPond's) position of the object
	initX = parseFloat(this.getAttribute("init-x"));
	initY = parseFloat(this.getAttribute("init-y"));
  
  // determine the current position at the start of a (new) drag
  var startPos = getTranslPos(this);
  startX = startPos.x;
  startY = startPos.y;
  objTransform = startPos.tr;
  //catch type of element [preliminary]
  pyLinks.dragElement(this.nodeName)
    
  // where is the initial object position related to the original position?
  startOffX = getRoundDiffPos(startX, initX);
  startOffY = getRoundDiffPos(initY, startY);

  // announce original position (may already have an offset)
  pyLinks.startDragging(startOffX, startOffY);
  
  //ensure that the selected element will always be on top by putting it last in the node list
  //Clone the node to make sure we can put it back when drag is finished
  clone = this.cloneNode(true);
  this.parentNode.replaceChild(clone, this);
  svg.appendChild(this);
  
  //prepare deletion
  delNode = this;
  
  //make the clone transparent
  //This can be set to 0 to preserve previous behaviour,
  //but I think this has a nice touch.
  clone.setAttribute("opacity", "0.3");
  

}

function MouseMove(e){
  e.stopPropagation();
  // ignore events from other objects than the dragged one
  // This doesn't work reliably yet. When an object is dragged
  // _under_ another one the event is only triggered for the wrong one.
  if (e.target == draggedObject){
    // calculate mouse coordinates relative to the drag's starting position
    calcPositions(e);
    
    // move the object to the new position
    objTransform.setTranslate(currX, currY);
      
    // announce the new position
    pyLinks.dragging(currOffX, currOffY);
  }
}

function MouseUp(e){
	
	//set the new position for the clone
	var clonePos = getTranslPos(clone);
	cloneTransform = clonePos.tr;
	cloneTransform.setTranslate(currX, currY);
	
	//remove transparency
	clone.removeAttribute("opacity");
  
	//change color when object is modified
    if(clone.getAttribute("fill") != "orange"){
		clone.setAttribute("fill", "orange");
	}
	
	//enable further editing
	enableMouseEvents(clone);
        
    // calculate positions, is only necessary for the signal
    calcPositions(e);
    pyLinks.dragged(currOffX, currOffY);
        
    // clean up
    draggedObject = null;
    dragOrigin = null;
    svg.removeChild(delNode);
}

//mouse position
function mousePos(event) {
	var svgPoint = svg.createSVGPoint();

    svgPoint.x = event.clientX;
    svgPoint.y = event.clientY;

    svgPoint = svgPoint.matrixTransform(svg.getScreenCTM().inverse());
    
    return svgPoint;
}

//get markup translate coordinates
function getTranslPos(elem){
	var tr = elem.transform.baseVal.getItem(0);
	if (tr.type == SVGTransform.SVG_TRANSFORM_TRANSLATE){
		return { 
			x: tr.matrix.e, y: tr.matrix.f, tr: tr
		}
	}
}

//return rounded difference between initial and current position 
function getRoundDiffPos(p, initP){
	return roundPos(p - initP);
}

//round position to two decimals	
function roundPos(pos){
	return Math.round(pos * 100) / 100;
}


